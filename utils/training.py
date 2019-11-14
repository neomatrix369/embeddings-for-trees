from typing import List, Dict

import dgl
import torch
import torch.nn as nn
from numpy import cumsum

from model.tree2seq import Tree2Seq
from utils.metrics import calculate_batch_statistics
from utils.common import SOS, EOS, UNK, PAD


def convert_labels(labels: List[str], label_to_sublabel: Dict, sublabel_to_id: Dict) -> torch.Tensor:
    """Create target tensor from list of labels

    :param sublabel_to_id: map for sublabel to int
    :param label_to_sublabel: corresponding list of sublabels
    :param labels: list of labels [batch size]
    :return target tensor with [max sequence length, batch size]
    """
    sublabels_length = torch.tensor([label_to_sublabel[label].shape[0] for label in labels])
    max_sublabel_length = sublabels_length.max()
    torch_labels = torch.full((max_sublabel_length.item() + 2, len(labels)), sublabel_to_id[PAD],
                              dtype=torch.long)
    torch_labels[0, :] = sublabel_to_id[SOS]
    torch_labels[sublabels_length + 1, torch.arange(0, len(labels))] = sublabel_to_id[EOS]
    for sample, label in enumerate(labels):
        torch_labels[1:sublabels_length[sample] + 1, sample] = label_to_sublabel[label]
    return torch_labels


def get_root_indexes(graph: dgl.BatchedDGLGraph) -> torch.Tensor:
    """Get indexes of roots in given graph

    :param graph: batched dgl graph
    :return: tensor with indexes of roots [batch size]
    """
    mask = torch.zeros(graph.number_of_nodes())
    idx_of_roots = cumsum([0] + graph.batch_num_nodes)[:-1]
    mask[idx_of_roots] = 1
    root_indexes = torch.nonzero(mask).squeeze(1)
    return root_indexes


def train_on_batch(
        model: Tree2Seq, criterion: nn.modules.loss, optimizer: torch.optim,
        graph: dgl.BatchedDGLGraph, labels: List[str],
        label_to_sublabel: Dict, sublabel_to_id: Dict,
        params: Dict, device: torch.device
) -> Dict:
    model.train()

    ground_truth = convert_labels(labels, label_to_sublabel, sublabel_to_id).to(device)
    root_indexes = get_root_indexes(graph).to(device)

    # Model step
    model.zero_grad()
    root_logits = model(graph, root_indexes, ground_truth, device)
    root_logits = root_logits[1:]
    ground_truth = ground_truth[1:]
    loss = criterion(root_logits.view(-1, root_logits.shape[-1]), ground_truth.view(-1))
    loss.backward()
    nn.utils.clip_grad_norm_(model.parameters(), params['clip_norm'])
    optimizer.step()

    # Calculate metrics
    prediction = model.predict(root_logits)
    batch_train_info = {
        'loss': loss.item(),
        'batch_count': 1,
        'statistics':
            calculate_batch_statistics(
                ground_truth, prediction, [sublabel_to_id[token] for token in [PAD, UNK, EOS]]
            )
    }
    return batch_train_info