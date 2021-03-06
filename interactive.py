import os
from argparse import ArgumentParser
from itertools import takewhile

import torch
from dgl.data.utils import load_graphs

from data_preprocessing.dot2dgl import convert_project
from data_preprocessing.preprocess_steps import build_asts
from model.tree2seq import Tree2Seq
from utils.common import fix_seed, get_device, create_folder, EOS

TMP_FOLDER = '.tmp'
ASTMINER_PATH = 'utils/astminer-cli.jar'
ASTMINER_PARAMS = ['--storage', 'dot', '--granularity', 'method', '--lang', 'java', '--hide-method-name',
                   '--split-tokens', '--java-parser', 'gumtree', '--remove-nodes', 'Javadoc']


def interactive(path_to_function: str, path_to_model: str):
    fix_seed()
    device = get_device()
    print(f"using {device} device")

    # load model
    print("loading model...")
    checkpoint = torch.load(path_to_model, map_location=device)

    model = Tree2Seq(**checkpoint['configuration']).to(device)
    model.load_state_dict(checkpoint['state_dict'])

    token_to_id = model.token_to_id
    type_to_id = model.type_to_id
    label_to_id = model.label_to_id
    id_to_label = {v: k for k, v in label_to_id.items()}

    # convert function to dgl format
    print("convert function to dgl format...")
    create_folder(TMP_FOLDER)
    build_asts(path_to_function, TMP_FOLDER, ASTMINER_PATH, *ASTMINER_PARAMS)
    project_folder = os.path.join(TMP_FOLDER, 'java')
    convert_project(project_folder, token_to_id, type_to_id, label_to_id, True, True, 5, 6, False, True, '|')

    # load function
    graph, labels = load_graphs(os.path.join(project_folder, 'converted.dgl'))
    labels = labels['labels']
    assert len(labels) == 1, f"found {len('labels')} functions, instead of 1"
    ast = graph[0].reverse(share_ndata=True)
    ast.ndata['token'] = ast.ndata['token'].to(device)
    ast.ndata['type'] = ast.ndata['type'].to(device)
    labels = labels.t().to(device)
    root_indexes = torch.tensor([0], dtype=torch.long)

    # forward pass
    model.eval()
    with torch.no_grad():
        logits = model(ast, root_indexes, labels, device)
    logits = logits[1:]
    prediction = model.predict(logits).reshape(-1)
    sublabels = [id_to_label[label_id.item()] for label_id in prediction]
    label = '|'.join(takewhile(lambda sl: sl != EOS, sublabels))
    print(f"the predicted label is:\n{label}")


if __name__ == '__main__':
    arg_parser = ArgumentParser(description=f"predict function name for given function by given model")
    arg_parser.add_argument("function", type=str, help="path to the file with function")
    arg_parser.add_argument("model", type=str, help="path to the frozen model")

    args = arg_parser.parse_args()
    interactive(args.function, args.model)
