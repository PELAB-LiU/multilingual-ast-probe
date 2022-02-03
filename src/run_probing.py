import os
import argparse
import logging
from typing import Union

import torch
from torch.utils.data import DataLoader
from transformers import AutoModel, AutoTokenizer, RobertaModel
from datasets import load_dataset
from tree_sitter import Parser
from tqdm import tqdm

from data import convert_sample_to_features, PY_LANGUAGE, collator_fn
from probe import TwoWordPSDProbe, L1DistanceLoss, get_embeddings, align_function, report_uas


logger = logging.getLogger(__name__)

#I assume that it is a roberta model
def generate_baseline(model):
    config = model.config
    baseline = RobertaModel(config)
    baseline.embeddings = model.embeddings
    return baseline

def run_probing_train(args: argparse.Namespace):
    logger.info('-' * 100)
    logger.info('Running probing training.')
    logger.info('-' * 100)

    logger.info('Loading dataset from local file.')
    data_files = {'train': os.path.join(args.dataset_name_or_path, 'train.jsonl'),
                  'valid': os.path.join(args.dataset_name_or_path, 'valid.jsonl'),
                  'test': os.path.join(args.dataset_name_or_path, 'test.jsonl')}

    #load, filter, shuffle, get
    train_set = load_dataset('json', data_files=data_files, split='train')
    train_set = train_set.filter(lambda e: len(e['code_tokens']) <= 100)
    train_set = train_set.shuffle(args.seed)
    train_set = train_set[0:20000]
    valid_set = load_dataset('json', data_files=data_files, split='valid')
    valid_set = valid_set.filter(lambda e: len(e['code_tokens']) <= 100)
    valid_set = valid_set.shuffle(args.seed)
    valid_set = valid_set[0:2000]
    test_set = load_dataset('json', data_files=data_files, split='test')
    test_set = test_set.filter(lambda e: len(e['code_tokens']) <= 100)
    test_set = test_set.shuffle(args.seed)
    test_set = test_set[0:4000]


    # @todo: load from checkpoint
    logger.info('Loading model and tokenizer.')
    tokenizer = AutoTokenizer.from_pretrained(args.pretrained_model_name_or_path)

    lmodel = AutoModel.from_pretrained(args.pretrained_model_name_or_path, output_hidden_states=True)
    if args.run_name.endswith('-baseline'):
        lmodel = generate_baseline(lmodel)

    #parse to distance matrices
    parser = Parser()
    parser.set_language(PY_LANGUAGE)
    train_set = train_set.map(lambda e: convert_sample_to_features(e['original_string'], parser))
    train_set = train_set.remove_columns('original_string')
    valid_set = valid_set.map(lambda e: convert_sample_to_features(e['original_string'], parser))
    valid_set = valid_set.remove_columns('original_string')
    test_set = test_set.map(lambda e: convert_sample_to_features(e['original_string'], parser))
    test_set = test_set.remove_columns('original_string')

    train_dataloader = DataLoader(dataset=train_set,
                                  batch_size=32,
                                  shuffle=True,
                                  collate_fn=lambda batch: collator_fn(batch, tokenizer),
                                  num_workers=10)
    valid_dataloader = DataLoader(dataset=valid_set,
                                  batch_size=32,
                                  shuffle=False,
                                  collate_fn=lambda batch: collator_fn(batch, tokenizer),
                                  num_workers=10)
    test_dataloader = DataLoader(dataset=test_set,
                                  batch_size=32,
                                  shuffle=False,
                                  collate_fn=lambda batch: collator_fn(batch, tokenizer),
                                  num_workers=10)

    probe_model = TwoWordPSDProbe(128, 768, args.device)
    criterion = L1DistanceLoss(args.device)

    optimizer = torch.optim.Adam(probe_model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.1, patience=0)

    probe_model.train()
    lmodel.eval()
    best_eval_loss = float('inf')
    patience_count = 0
    for epoch in tqdm(range(args.epochs), desc='[training epoch loop]'):
        training_loss = 0.0
        step_loss, step_num = 0.0, 0
        for step, batch in enumerate(tqdm(train_dataloader,
                                          desc='[training batch]',
                                          bar_format='{desc:<10}{percentage:3.0f}%|{bar:100}{r_bar}')):
            all_inputs, all_attentions, dis, lens, alig = batch

            emb = get_embeddings(all_inputs, all_attentions, lmodel, args.layer)
            emb = align_function(emb, alig)

            outputs = probe_model(emb.to(args.device))
            loss, count = criterion(outputs, dis.to(args.device), lens.to(args.device))

            step_loss += loss.item()
            step_num += 1
            if step % 10 == 0 and step > 0:
                avg_loss = round(step_loss / step_num, 4)
                logger.info(f'\nepoch {epoch} step {step} loss {avg_loss}')
                step_loss, step_num = 0, 0

            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            training_loss += loss.item()

        training_loss = training_loss / len(train_dataloader)
        eval_loss = run_probing_eval(valid_dataloader, probe_model, criterion, lmodel, args.layer, args)
        #compute the UAS in the eval set
        eval_uas = report_uas(valid_dataloader, probe_model, lmodel, args)
        scheduler.step(eval_loss)
        logger.info(f'[epoch {epoch}] train loss: {training_loss}, validation loss: {eval_loss}, validation UAS: {eval_uas}')

        if eval_loss < best_eval_loss:
            logger.info('-' * 100)
            logger.info('Saving model checkpoint')
            logger.info('-' * 100)
            output_path = os.path.join(args.model_chkpt_path, f'pytorch_model.bin')
            torch.save(probe_model.state_dict(), output_path)
            logger.info(f'Probe model saved: {output_path}')
            patience_count = 0
            best_eval_loss = eval_loss
        else:
            patience_count += 1
        if patience_count == args.patience:
            break

    #Load final model and test it over the test set (i.e., UAS)
    logger.info('-' * 100)
    logger.info(f'Loading best probe')
    final_probe_model = TwoWordPSDProbe(128, 768, args.device)
    final_probe_model.load_state_dict(torch.load(os.path.join(args.model_chkpt_path, f'pytorch_model.bin')))
    uas_test = report_uas(test_dataloader, final_probe_model, lmodel, args)
    logger.info(f'Test UAS: {eval_uas}')


def run_probing_eval(
        test_dataloader: Union[DataLoader, None] = None,
        probe_model: Union[TwoWordPSDProbe, None] = None,
        criterion: Union[L1DistanceLoss, None] = None,
        lmodel: Union[AutoModel, None] = None,
        layer: Union[int, None] = None,
        args: Union[argparse.Namespace, None] = None):
    probe_model.eval()
    eval_loss = 0.0
    with torch.no_grad():
        for batch in tqdm(test_dataloader, desc='[valid batch]'):
            all_inputs, all_attentions, dis, lens, alig = batch
            emb = get_embeddings(all_inputs, all_attentions, lmodel, layer)
            emb = align_function(emb, alig)
            outputs = probe_model(emb.to(args.device))
            loss, count = criterion(outputs, dis.to(args.device), lens.to(args.device))
            eval_loss += loss.item()
    return eval_loss / len(test_dataloader)
