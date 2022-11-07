import argparse
import glob
import os
import pickle

import pandas as pd
from plotnine import ggplot, aes, geom_line, scale_x_continuous, labs, theme, element_text


def read_results(args):
    data = {'model': [], 'lang': [], 'layer': [], 'rank': [],
            'precision': [], 'recall': [], 'f1': []}
    for file in glob.glob(args.run_dir + "/*/metrics.log"):
        parent = os.path.dirname(file).split('/')[-1]
        model, lang, layer, rank = parent.split('_')
        with open(file, 'rb') as f:
            results = pickle.load(f)
        data['model'].append(model)
        data['lang'].append(lang)
        data['layer'].append(int(layer))
        data['rank'].append(int(rank))
        data['precision'].append(results['test_precision'])
        data['recall'].append(results['test_recall'])
        data['f1'].append(results['test_f1'])
    df = pd.DataFrame(data)
    df_renamed = df.replace({'codebert': 'CodeBERT',
                             'codebert-baseline': 'CodeBERTrand',
                             'codeberta': 'CodeBERTa',
                             'codet5': 'CodeT5',
                             'graphcodebert': 'GraphCodeBERT',
                             'roberta': 'RoBERTa'})
    return df_renamed


def main(args):
    results = read_results(args)
    for lang in ['python', 'java', 'ruby', 'javascript']:
        layer_vs_f1 = (
                ggplot(results[(results['lang'] == lang)])
                + aes(x="layer", y="f1", color='model')
                + geom_line()
                + scale_x_continuous(breaks=range(0, 13, 1))
                + labs(x="Layer", y="F1", color="Model")
                + theme(text=element_text(size=16))
        )
        layer_vs_f1.save(f"layer_vs_f1_{lang}.pdf", dpi=600)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script for analyzing the results')
    parser.add_argument('--run_dir', default='./runs', help='Path of the run logs')
    args = parser.parse_args()
    main(args)