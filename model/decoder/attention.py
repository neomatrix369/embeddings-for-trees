from math import sqrt
from typing import List

import torch
import torch.nn as nn
import torch.nn.functional as f

from utils.common import segment_sizes_to_slices


class _IAttention(nn.Module):
    def __init__(self, h_enc: int, h_dec: int) -> None:
        super().__init__()
        self.h_enc = h_enc
        self.h_dec = h_dec

    def forward(self, hidden_states: torch.Tensor, encoder_output: torch.Tensor, tree_sizes: List)\
            -> torch.Tensor:
        """ Compute attention weights based on previous decoder state and encoder output

        :param hidden_states: [batch size, hidden size]
        :param encoder_output: [number of nodes in batch, hidden size]
        :param tree_sizes: [batch size]
        :return: attention weights [number of nodes in batch, 1]
        """
        raise NotImplementedError


class LuongAttention(_IAttention):
    def __init__(self, h_enc: int, h_dec: int, score: str = 'concat') -> None:
        super().__init__(h_enc, h_dec)
        self.score = score
        if self.score == 'concat':
            self.linear = nn.Linear(self.h_dec + self.h_enc, self.h_enc, bias=False)
            self.v = nn.Parameter(torch.rand(self.h_enc, 1), requires_grad=True)
        elif self.score == 'general':
            self.linear = nn.Linear(self.h_enc, h_dec, bias=False)
        else:
            raise ValueError(f"Unknown score function: {score}")

    def forward(self, hidden_states: torch.Tensor, encoder_output: torch.Tensor, tree_sizes: List)\
            -> torch.Tensor:
        # [number of nodes in batch, h_dec]
        repeated_hidden_states = torch.cat(
            [prev_hidden_state.expand(tree_size, -1)
             for prev_hidden_state, tree_size in zip(hidden_states, tree_sizes)],
            dim=0
        )

        if self.score == 'concat':
            # [number of nodes in batch, h_enc]
            energy = torch.tanh(self.linear(
                torch.cat((repeated_hidden_states, encoder_output), dim=1)
            ))
            # [number of nodes in batch, 1]
            scores = torch.matmul(energy, self.v)
        elif self.score == 'general':
            # [number of nodes in batch; h dec]
            linear_encoder = self.linear(encoder_output)
            # [number of nodes in batch; 1]
            scores = torch.bmm(linear_encoder.unsqueeze(1), repeated_hidden_states.unsqueeze(2)).squeeze(2)
        else:
            raise RuntimeError("Oh, this is strange")

        # [number of nodes in batch, 1]
        attentions = torch.cat(
            [nn.functional.softmax(scores[tree_slice], dim=0)
             for tree_slice in segment_sizes_to_slices(tree_sizes)],
            dim=0
        )

        return attentions


def scaled_dot_product_attention(
        query: torch.Tensor, key: torch.Tensor, value: torch.Tensor,
        mask: torch.Tensor = None, dropout: nn.Dropout = None
) -> torch.Tensor:
    scores = query.matmul(key.transpose(-2, -1)) / sqrt(query.shape[-1])
    if mask is not None:
        scores = scores.masked_fill(mask == 0, -1e9)
    scores = f.softmax(scores, dim=-1)
    if dropout is not None:
        scores = dropout(scores)
    output = torch.matmul(scores, value)
    return output


def get_attention(attention: str) -> _IAttention:
    attentions = {
        LuongAttention.__name__: LuongAttention
    }
    if attention not in attentions:
        raise ValueError(f"unknown attention mechanism: {attention}")
    return attentions[attention]