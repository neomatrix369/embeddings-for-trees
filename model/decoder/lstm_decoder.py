from typing import Union, Tuple, Dict

import torch
from torch import nn

from model.attention import Attention
from model.decoder import ITreeDecoder
from utils.common import segment_sizes_to_slices


class LSTMDecoder(ITreeDecoder):

    name = "LSTM"

    def __init__(
            self, h_enc: int, h_dec: int, label_to_id: Dict, dropout: float = 0.,
            teacher_force: float = 0., attention: Dict = None
    ):
        """Convert label to consequence of sublabels and use lstm cell to predict next

        :param h_enc: encoder hidden state, correspond to hidden state of LSTM cell
        :param h_dec: size of LSTM cell input/output
        :param label_to_id: dict for converting labels to ids
        :param dropout: probability of dropout
        :param teacher_force: probability of teacher forcing, 0 corresponds to always use previous predicted value
        :param attention: if passed, init attention with given args
        """
        super().__init__(h_enc, h_dec, label_to_id)
        self.teacher_force = teacher_force

        self.embedding = nn.Embedding(self.out_size, self.h_dec, padding_idx=self.pad_index)
        self.linear = nn.Linear(self.h_enc, self.out_size)
        self.dropout = nn.Dropout(dropout)

        self.use_attention = attention is not None
        if self.use_attention:
            self.attention = Attention(self.h_enc, self.h_dec, **attention)

        lstm_input_size = self.h_enc + self.h_dec if self.use_attention else self.h_dec
        self.lstm = nn.LSTM(input_size=lstm_input_size, hidden_size=self.h_enc)

    def forward(
            self, encoded_data: Union[torch.Tensor, Tuple[torch.Tensor, ...]],
            root_indexes: torch.LongTensor, labels: torch.Tensor
    ) -> torch.Tensor:
        if isinstance(encoded_data, torch.Tensor):
            encoded_data = (encoded_data,)
        if len(encoded_data) == 1:
            node_hidden_states = encoded_data[0]
            node_memory_states = encoded_data[0].new_zeros(encoded_data[0].shape, requires_grad=False)
        elif len(encoded_data) == 2:
            # [number of nodes, encoder hidden state]
            node_hidden_states, node_memory_states = encoded_data
        else:
            raise ValueError(f"Passed too much tensors to LSTM decoder: {len(encoded_data)}")

        # [1, batch size, encoder hidden state]
        root_hidden_states = node_hidden_states[root_indexes].unsqueeze(0)
        root_memory_states = node_memory_states[root_indexes].unsqueeze(0)

        max_length, batch_size = labels.shape
        # [the longest sequence, batch size, vocab size]
        outputs = node_hidden_states.new_zeros((max_length, batch_size, self.out_size))

        tree_sizes = [(root_indexes[i] - root_indexes[i - 1]).item() for i in range(1, batch_size)]
        tree_sizes.append(node_hidden_states.shape[0] - root_indexes[-1].item())

        # labels[0] correspond to batch of <SOS> tokens
        # [batch size]
        current_input = labels[0]
        for step in range(1, max_length):
            # [1, batch size, decoder hidden state]
            embedded = self.embedding(current_input).unsqueeze(0)

            if self.use_attention:
                # [number of nodes]
                attention = self.attention(root_hidden_states[0], node_hidden_states, tree_sizes)

                # [number of nodes, encoder hidden size]
                weighted_hidden_states = node_hidden_states * attention

                # [1, batch size, encoder hidden size]
                attended_hidden_states = torch.cat(
                    [torch.sum(weighted_hidden_states[tree_slice], dim=0, keepdim=True)
                     for tree_slice in segment_sizes_to_slices(tree_sizes)],
                    dim=0
                ).unsqueeze(0)

                # [1, batch size, decoder hidden size + encoder hidden size]
                lstm_cell_input = torch.cat((embedded, attended_hidden_states), dim=2)
            else:
                # [1, batch size, decoder hidden size]
                lstm_cell_input = embedded

            lstm_cell_input = self.dropout(lstm_cell_input)

            # [1, batch size, encoder hidden state]
            current_output, (root_hidden_states, root_memory_states) = \
                self.lstm(lstm_cell_input, (root_hidden_states, root_memory_states))

            # [batch size, vocab size]
            current_output = self.linear(root_hidden_states.squeeze(0))
            outputs[step] = current_output

            if self.training:
                current_input = labels[step] if torch.rand(1) < self.teacher_force else current_output.argmax(dim=-1)
            else:
                current_input = current_output.argmax(dim=-1)

        if self.use_attention:
            del weighted_hidden_states
            del attention
            del attended_hidden_states
        del embedded
        del current_output
        return outputs
