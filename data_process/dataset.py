from os import listdir
from os.path import exists as path_exists
from os.path import join as path_join
from pickle import load as pkl_load
from typing import Tuple, List

from dgl import DGLGraph
from torch.utils.data import Dataset


class JavaDataset(Dataset):

    def __init__(self, path_to_batches: str) -> None:
        self.full_path = path_to_batches
        assert path_exists(self.full_path)
        self.batches = list(filter(lambda filename: filename.endswith('.pkl'), listdir(self.full_path)))

    def __len__(self) -> int:
        return len(self.batches)

    def __getitem__(self, item) -> Tuple[DGLGraph, List[str]]:
        with open(path_join(self.full_path, self.batches[item]), 'rb') as pkl_file:
            batch = pkl_load(pkl_file)
            return batch['batched_graph'], batch['labels']