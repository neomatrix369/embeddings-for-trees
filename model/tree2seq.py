from typing import Dict

import torch
import torch.nn as nn
from dgl import BatchedDGLGraph

from model.decoder import _IDecoder, LinearDecoder
from model.embedding import _IEmbedding, FullTokenEmbedding, SubTokenEmbedding
from model.encoder import _IEncoder
from model.treelstm import TreeLSTM


class Tree2Seq(nn.Module):
    def __init__(self, embedding: _IEmbedding, encoder: _IEncoder, decoder: _IDecoder) -> None:
        super().__init__()
        self.embedding = embedding
        self.encoder = encoder
        self.decoder = decoder

    def forward(self,
                graph: BatchedDGLGraph, root_indexes: torch.LongTensor,
                ground_truth: torch.Tensor, device: torch.device) -> torch.Tensor:
        """

        :param graph: the batched graph with function's asts
        :param root_indexes: indexes of roots in the batched graph
        :param ground_truth: [length of the longest sequence, batch size]
        :param device: torch device
        :return: [length of the longest sequence, batch size, number of classes] logits for each element in sequence
        """
        embedded_graph = self.embedding(graph)
        node_hidden_states, node_memory_cells = self.encoder(embedded_graph, device)
        root_hidden_states = node_hidden_states[root_indexes]
        root_memory_cells = node_memory_cells[root_indexes]

        max_length, batch_size = ground_truth.shape
        outputs = torch.zeros(max_length, batch_size, self.decoder.out_size).to(device)

        current_input = ground_truth[0:]
        for step in range(1, max_length):
            output, root_hidden_states, root_memory_cells =\
                self.decoder(current_input, root_hidden_states, root_memory_cells)

            outputs[step] = output
            current_input = ground_truth[step]

        return outputs

    @staticmethod
    def predict(logits: torch.Tensor) -> torch.Tensor:
        """Predict token for each step by given logits

        :param logits: [max length, batch size, number of classes] logits for each position in sequence
        :return: [max length, batch size] token's ids for each position in sequence
        """
        tokens_probas = nn.functional.softmax(logits, dim=-1)
        return tokens_probas.argmax(dim=-1)


class ModelFactory:

    _embeddings = {
        'FullTokenEmbedding': FullTokenEmbedding,
        'SubTokenEmbedding': SubTokenEmbedding
    }
    _encoders = {
        'TreeLSTM': TreeLSTM
    }
    _decoders = {
        'LinearDecoder': LinearDecoder
    }

    def __init__(self, embedding_info: Dict, encoder_info: Dict, decoder_info: Dict):
        self.embedding_info = embedding_info
        self.encoder_info = encoder_info
        self.decoder_info = decoder_info

        self.embedding = self._get_module(self.embedding_info['name'], self._embeddings)
        self.encoder = self._get_module(self.encoder_info['name'], self._encoders)
        self.decoder = self._get_module(self.decoder_info['name'], self._decoders)

    @staticmethod
    def _get_module(module_name: str, modules_dict: Dict) -> nn.Module:
        if module_name not in modules_dict:
            raise ModuleNotFoundError(f"Unknown module {module_name}, try one of {', '.join(modules_dict.keys())}")
        return modules_dict[module_name]

    def construct_model(self, device: torch.device) -> Tree2Seq:
        return Tree2Seq(
            self.embedding(**self.embedding_info['params']),
            self.encoder(**self.encoder_info['params']),
            self.decoder(**self.decoder_info['params']),
        ).to(device)