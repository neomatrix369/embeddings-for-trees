from argparse import ArgumentParser
from json import load as json_load
from pickle import load as pkl_load
from typing import Dict

import numpy as np
import torch
import torch.nn as nn
from numpy import cumsum
from tqdm.auto import tqdm

from data_workers.dataset import JavaDataset
from model.model_factory import ModelFactory
from utils.common import fix_seed, get_device


def train(params: Dict) -> None:
    fix_seed()
    device = get_device()
    print(f"using {device} device")

    training_set = JavaDataset(params['paths']['train_batches'], params['batch_size'], True)
    validation_set = JavaDataset(params['paths']['validation_batches'], params['batch_size'], True)

    with open(params['paths']['labels_path'], 'rb') as pkl_file:
        label_to_id = pkl_load(pkl_file)

    with open(params['paths']['vocabulary_path'], 'rb') as pkl_file:
        vocabulary = pkl_load(pkl_file)
        token_to_id = vocabulary['token_to_id']
        type_to_id = vocabulary['type_to_id']

    # create models
    params['embedding']['params']['token_vocab_size'] = len(token_to_id)
    params['embedding']['params']['type_vocab_size'] = len(type_to_id)
    params['decoder']['params']['out_size'] = len(label_to_id)
    model_factory = ModelFactory(params['embedding'], params['encoder'], params['decoder'], device)
    model: nn.Module = model_factory.construct_model()

    # create optimizers
    optimizer = torch.optim.RMSprop(
        model.parameters(), lr=params['lr'], weight_decay=params['weight_decay']
    )

    # define loss function
    criterion = nn.CrossEntropyLoss()

    # train loop
    print("starting train loop...")
    for epoch in range(params['n_epochs']):
        running_loss = 0.0
        correct_per_epoch = 0
        number_of_samples = 0
        batch_indexes = np.arange(len(training_set))
        np.random.shuffle(batch_indexes)
        for batch_id in tqdm(batch_indexes):
            graph, labels = training_set[batch_id]
            torch_labels = torch.tensor([label_to_id.get(label, 0) for label in labels]).to(device)

            mask = torch.zeros(graph.number_of_nodes())
            idx_of_roots = cumsum([0] + graph.batch_num_nodes)[:-1]
            mask[idx_of_roots] = 1
            root_indexes = torch.nonzero(mask).squeeze(1).to(device)

            model.zero_grad()

            root_logits = model(graph, root_indexes)
            prediction = model.predict(root_logits)

            loss = criterion(root_logits, torch_labels)
            loss.backward()

            nn.utils.clip_grad_norm_(model.parameters(), 5)

            optimizer.step()

            running_loss += loss.item()
            correct_per_epoch += prediction.eq(torch_labels).sum().item()
            number_of_samples += torch_labels.shape[0]
            print(loss.item(), correct_per_epoch / number_of_samples)
        print(f"epoch #{epoch} -- loss: {running_loss}")


if __name__ == '__main__':
    arg_parse = ArgumentParser()
    arg_parse.add_argument('--config', type=str, required=True, help='path to config json')
    args = arg_parse.parse_args()

    with open(args.config) as config_file:
        train(json_load(config_file))

