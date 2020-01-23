from typing import Tuple

import dgl
import torch
import torch.nn as nn

from model.encoder import _IEncoder
from model.treeLSTM_cell import ChildSumTreeLSTMCell


class TokenTreeLSTM(_IEncoder):

    def __init__(self, h_emb: int, h_enc: int, dropout_prob: float = 0.) -> None:
        super().__init__(h_emb, h_enc)
        self.cell = ChildSumTreeLSTMCell(self.h_emb, self.h_enc)
        self.dropout = nn.Dropout(dropout_prob)

    def forward(self, batch: dgl.BatchedDGLGraph, device: torch.device) -> Tuple[torch.Tensor, torch.Tensor]:
        dropout_tokens = self.dropout(batch.ndata['token_embeds'])
        batch.ndata['x'] = dropout_tokens
        return self.cell(batch, device)


class TokenTypeTreeLSTM(_IEncoder):

    def __init__(self, h_emb: int, h_enc: int, dropout_prob: float = 0.) -> None:
        super().__init__(h_emb, h_enc)
        self.cell = ChildSumTreeLSTMCell(self.h_enc, self.h_enc)
        self.dropout = nn.Dropout(dropout_prob)
        self.linear = nn.Linear(2 * self.h_emb, self.h_enc)
        self.tanh = nn.Tanh()

    def forward(self, batch: dgl.BatchedDGLGraph, device: torch.device) -> Tuple[torch.Tensor, torch.Tensor]:
        features = self.tanh(
            self.linear(
                torch.cat([batch.ndata['token_embeds'], batch.ndata['type_embeds']], 1)
            )
        )
        batch.ndata['x'] = self.dropout(features)
        return self.cell(batch, device)
