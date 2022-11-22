import argparse
import os
import pickle
from collections import defaultdict

import numpy as np
import torch
from matplotlib import pyplot as plt
from sklearn import metrics
from sklearn.manifold import TSNE

from src.data import LANGUAGES_CSN
from src.probe import ParserProbe


def load_labels(args):
    labels_file_path_c = os.path.join(args.run_folder, 'global_labels_c.pkl')
    labels_file_path_u = os.path.join(args.run_folder, 'global_labels_u.pkl')
    with open(labels_file_path_c, 'rb') as f:
        labels_to_ids_c = pickle.load(f)
    with open(labels_file_path_u, 'rb') as f:
        labels_to_ids_u = pickle.load(f)
    ids_to_labels_c = {y: x for x, y in labels_to_ids_c.items()}
    ids_to_labels_u = {y: x for x, y in labels_to_ids_u.items()}
    return labels_to_ids_c, ids_to_labels_c, labels_to_ids_u, ids_to_labels_u


def load_vectors(args, labels_to_ids_c, labels_to_ids_u):
    final_probe_model = ParserProbe(
        probe_rank=args.rank,
        hidden_dim=args.hidden,
        number_labels_c=len(labels_to_ids_c),
        number_labels_u=len(labels_to_ids_u)).to('cpu')
    final_probe_model.load_state_dict(torch.load(os.path.join(args.run_folder, f'pytorch_model.bin'),
                                                 map_location=torch.device('cpu')))
    vectors_c = final_probe_model.vectors_c.detach().cpu().numpy().T
    vectors_u = final_probe_model.vectors_u.detach().cpu().numpy().T
    return vectors_c, vectors_u


def compute_distances(vectors, ids_to_labels):
    vectors_per_lang = defaultdict(list)
    for idx in range(len(ids_to_labels)):
        lang = ids_to_labels[idx].split('--')[1]
        vectors_per_lang[lang].append(vectors[idx])
    vectors_per_lang = {x: np.mean(y, axis=0) for x, y in vectors_per_lang.items()}
    for x in LANGUAGES_CSN:
        for y in LANGUAGES_CSN:
            print(f'Distance between {x} and {y}: {np.linalg.norm(vectors_per_lang[x] - vectors_per_lang[y])}')


COLORS = {'java': 'r',
          'javascript': 'b',
          'go': 'g',
          'python': 'c',
          'c': 'm',
          'ruby': 'y',
          'csharp': 'k',
          'php': 'tab:pink'}


def run_tsne(vectors, ids_to_labels, model, perplexity=30, type_labels='constituency'):
    # vectors = vectors / np.linalg.norm(vectors, axis=1)[:, np.newaxis]
    v_2d = TSNE(n_components=2, learning_rate='auto', perplexity=perplexity,
                init='random', random_state=args.seed).fit_transform(vectors)
    figure, axis = plt.subplots(1, figsize=(20, 20))
    axis.set_title(f"Vectors {type_labels}")
    for ix, label in ids_to_labels.items():
        l = label.split('--')[1]
        axis.scatter(v_2d[ix, 0], v_2d[ix, 1], color=COLORS[l], label=l)
    plt.show()
    plt.savefig(f'vectors_{type_labels}_{model}.png')


def compute_clustering_quality(vectors, ids_to_labels, metric='silhouette'):
    # vectors = vectors / np.linalg.norm(vectors, axis=1)[:, np.newaxis]
    labels = []
    for idx in range(len(ids_to_labels)):
        lang = ids_to_labels[idx].split('--')[1]
        labels.append(lang)
    if metric == 'silhouette':
        print(f'silhouette: {metrics.silhouette_score(vectors, labels)}')


def main(args):
    labels_to_ids_c, ids_to_labels_c, labels_to_ids_u, ids_to_labels_u = load_labels(args)
    vectors_c, vectors_u = load_vectors(args, labels_to_ids_c, labels_to_ids_u)
    run_tsne(vectors_c, ids_to_labels_c, args.model, perplexity=30, type_labels='constituency')
    run_tsne(vectors_u, ids_to_labels_u, args.model, perplexity=5, type_labels='unary')
    compute_clustering_quality(vectors_c, ids_to_labels_c)
    compute_distances(vectors_c, ids_to_labels_c)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script for analyzing the results')
    parser.add_argument('--run_folder', help='Run folder of the multilingual probe')
    parser.add_argument('--model', help='Model name')
    parser.add_argument('--rank', default=128)
    parser.add_argument('--hidden', default=768)
    parser.add_argument('--seed', default=123)
    args = parser.parse_args()
    main(args)
