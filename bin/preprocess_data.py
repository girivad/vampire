import os
import re
import sys
import string
from optparse import OptionParser
from collections import Counter

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.io import savemat
from tqdm import tqdm
import common.file_handling as fh
import argparse
from shutil import copyfile


punct_chars = list(set(string.punctuation) - set("'"))
punct_chars.sort()
punctuation = ''.join(punct_chars)
replace = re.compile('[%s]' % re.escape(punctuation))
alpha = re.compile('^[a-zA-Z_]+$')
alpha_or_num = re.compile('^[a-zA-Z_]+|[0-9_]+$')
alphanum = re.compile('^[a-zA-Z0-9_]+$')

def preprocess_data(train_infile: str,
                    test_infile: str,
                    dev_infile: str,
                    output_dir: str,
                    train_prefix: str,
                    test_prefix: str,
                    dev_prefix: str,
                    min_doc_count: int=0,
                    max_doc_freq: int=1.0,
                    vocab_size: int=None,
                    sample: int=None,
                    stopwords: str=None,
                    keep_num: bool=False,
                    keep_alphanum: bool=False,
                    strip_html: bool=False,
                    lower: bool=True,
                    min_length: int=3,
                    label_field: str=None):

    if stopwords == 'mallet':
        print("Using Mallet stopwords")
        stopword_list = fh.read_text("/home/ubuntu/vae/" + os.path.join('common', 'stopwords', 'mallet_stopwords.txt'))
    elif stopwords == 'snowball':
        print("Using snowball stopwords")
        stopword_list = fh.read_text("/home/ubuntu/vae/" + os.path.join('common', 'stopwords', 'snowball_stopwords.txt'))
    elif stopwords is not None:
        print("Using custom stopwords")
        stopword_list = fh.read_text("/home/ubuntu/vae/" + os.path.join('common', 'stopwords', stopwords + '_stopwords.txt'))
    else:
        stopword_list = []
    stopword_set = {s.strip() for s in stopword_list}

    print("Reading data files")

    train_items = fh.read_jsonlist(train_infile, sample=sample)
    n_train = len(train_items)
    print("Found {:d} training documents".format(n_train))

    if test_infile is not None:
        test_items = fh.read_jsonlist(test_infile)
        n_test = len(test_items)
        print("Found {:d} test documents".format(n_test))
    else:
        test_items = []
        n_test = 0

    if dev_infile is not None:
        dev_items = fh.read_jsonlist(dev_infile)
        n_dev = len(dev_items)
        print("Found {:d} dev documents".format(n_dev))
    else:
        dev_items = []
        n_dev = 0

    all_items = train_items + test_items + dev_items
    all_items_dict = {"train" : train_items, "test": test_items, "dev": dev_items}

    n_items = n_train + n_test + n_dev

    label_lists = {}
    if label_field is not None:
        label_field = [label_field]
        for label_name in label_field:
            label_set = set()
            for i, item in enumerate(all_items):
                if label_name is not None:
                    label_set.add(str(item[label_name]))
            label_list = list(label_set)
            label_list.sort()
            n_labels = len(label_list)
            print("Found label %s with %d classes" % (label_name, n_labels))
            label_lists[label_name] = label_list
    else:
        label_field = []

    # make vocabulary
    train_parsed = []
    test_parsed = []
    dev_parsed = []

    print("Parsing %d documents" % n_items)
    word_counts = Counter()
    doc_counts = Counter()
    count = 0

    vocab = None
    for data_name, items in tqdm(all_items_dict.items()):
        for item in tqdm(items):
            text = item['tokens']
            tokens, _ = tokenize(text,
                                 strip_html=strip_html,
                                 lower=lower,
                                 keep_numbers=keep_num,
                                 keep_alphanum=keep_alphanum,
                                 min_length=min_length,
                                 stopwords=stopword_set,
                                 vocab=vocab)

            # store the parsed documents
            if data_name == 'train':
                train_parsed.append(tokens)
            elif data_name == 'test':
                test_parsed.append(tokens)
            elif data_name == 'dev':
                dev_parsed.append(tokens)
            if data_name == 'train':
                # keep track of the number of documents with each word
                word_counts.update(tokens)
                doc_counts.update(set(tokens))

    print("Size of full vocabulary=%d" % len(word_counts))

    print("Selecting the vocabulary")
    most_common = doc_counts.most_common()
    words, doc_counts = zip(*most_common)
    doc_freqs = np.array(doc_counts) / float(n_items)
    vocab = [word for i, word in enumerate(words) if doc_counts[i] >= min_doc_count and doc_freqs[i] <= max_doc_freq]
    most_common = [word for i, word in enumerate(words) if doc_freqs[i] > max_doc_freq]
    if max_doc_freq < 1.0:
        print("Excluding words with frequency > {:0.2f}:".format(max_doc_freq), most_common)

    print("Vocab size after filtering = %d" % len(vocab))
    if vocab_size is not None:
        if len(vocab) > int(vocab_size):
            vocab = vocab[:int(vocab_size)]
    # convert to a sparse representation
    if "@@UNKNOWN@@" not in vocab:
        vocab.append("@@UNKNOWN@@")

    vocab_size = len(vocab)
    print("Final vocab size = %d" % vocab_size)

    print("Most common words remaining:", ' '.join(vocab[:10]))
    vocab.sort()

    process_subset(train_items, train_parsed, label_field, label_lists, vocab, output_dir, train_prefix)

    if n_test > 0:
        process_subset(test_items, test_parsed, label_field, label_lists, vocab, output_dir, test_prefix)

    if n_dev > 0:
        process_subset(dev_items, dev_parsed, label_field, label_lists, vocab, output_dir, dev_prefix)

    total = np.sum([c for k, c in word_counts.items()])
    freqs = {k: c / float(total) for k, c in word_counts.items()}
    fh.write_to_json(freqs, os.path.join(output_dir, train_prefix + '.bgfreq.json'))

    if not os.path.isdir(os.path.join(output_dir, 'vocabulary')):
        os.mkdir(os.path.join(output_dir, 'vocabulary'))
    fh.write_list_to_text(vocab, os.path.join(output_dir, 'vocabulary', 'tokens.txt'))
    fh.write_list_to_text(np.unique(np.array(label_field)), os.path.join(output_dir, 'vocabulary', 'labels.txt'))
    fh.write_list_to_text(["0", "1"], os.path.join(output_dir, 'vocabulary', 'is_labeled.txt'))
    fh.write_list_to_text(["full", "labels", "is_labeled"], os.path.join(output_dir, 'vocabulary', 'non_padded_namespaces.txt'))

    print("Done!")


def process_subset(items, parsed, label_field, label_lists, vocab, output_dir, output_prefix):
    n_items = len(items)
    vocab_size = len(vocab)
    vocab_index = dict(zip(vocab, range(vocab_size)))

    ids = []
    for i, item in enumerate(items):
        if 'id' in item:
            ids.append(item['id'])

    if len(ids) != n_items:
        ids = [str(i) for i in range(n_items)]

    # create a label index using string representations
    for label_field in label_field:
        label_list = label_lists[label_field]
        n_labels = len(label_list)
        label_list_strings = [str(label) for label in label_list]
        label_index = dict(zip(label_list_strings, range(n_labels)))

    lines = []
    tokens = []

    for i, words in tqdm(enumerate(parsed), total=len(parsed)):
        # get the vocab indices of words that are in the vocabulary
        word_subset = [word for word in words if word in vocab_index]
        if len(label_field) > 0:
            label = items[i][label_field[-1]]
        tokens.append({"text":" ".join(word_subset), "label": label_index[str(label)]})
        lines.append(" ".join(word_subset))

    fh.write_jsonlist(tokens, os.path.join(output_dir, output_prefix + '.jsonl'))
    fh.write_list_to_text(lines, os.path.join(output_dir, output_prefix + '.txt'))


def tokenize(text,
             strip_html=False,
             lower=True,
             keep_emails=False,
             keep_at_mentions=False,
             keep_numbers=False,
             keep_alphanum=False,
             min_length=3,
             stopwords=None,
             vocab=None):
    text = clean_text(text, strip_html, lower, keep_emails, keep_at_mentions)
    tokens = text.split()

    if stopwords is not None:
        tokens = ['_' if t in stopwords else t for t in tokens]

    # remove tokens that contain numbers
    if not keep_alphanum and not keep_numbers:
        tokens = [t if alpha.match(t) else '_' for t in tokens]

    # or just remove tokens that contain a combination of letters and numbers
    elif not keep_alphanum:
        tokens = [t if alpha_or_num.match(t) else '_' for t in tokens]

    # drop short tokens
    if min_length > 0:
        tokens = [t if len(t) >= min_length else '_' for t in tokens]

    counts = Counter()

    unigrams = [t for t in tokens if t != '_']
    counts.update(unigrams)

    if vocab is not None:
        tokens = [token for token in unigrams if token in vocab]
    else:
        tokens = unigrams

    return tokens, counts


def clean_text(text, strip_html=False, lower=True, keep_emails=False, keep_at_mentions=False):
    # remove html tags
    if strip_html:
        text = re.sub(r'<[^>]+>', '', text)
    else:
        # replace angle brackets
        text = re.sub(r'<', '(', text)
        text = re.sub(r'>', ')', text)
    # lower case
    if lower:
        text = text.lower()
    # eliminate email addresses
    if not keep_emails:
        text = re.sub(r'\S+@\S+', ' ', text)
    # eliminate @mentions
    if not keep_at_mentions:
        text = re.sub(r'\s@\S+', ' ', text)
    # replace underscores with spaces
    text = re.sub(r'_', ' ', text)
    # break off single quotes at the ends of words
    text = re.sub(r'\s\'', ' ', text)
    text = re.sub(r'\'\s', ' ', text)
    # remove periods
    text = re.sub(r'\.', '', text)
    # replace all other punctuation (except single quotes) with spaces
    text = replace.sub(' ', text)
    # remove single quotes
    text = re.sub(r'\'', '', text)
    # replace all whitespace with a single space
    text = re.sub(r'\s', ' ', text)
    # strip off spaces on either end
    text = text.strip()
    return text


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-d', '--data_dir', dest='data_dir', type=str, help='path to data directory', required=True)
    parser.add_argument('-o','--output_dir', type=str, help='output directory', required=True)
    parser.add_argument('-l','--label', type=str, help='label name', required=False, default='label')
    parser.add_argument('-v','--vocab_size', type=int, help='vocab size', required=True)
    parser.add_argument('-s','--subsamples', nargs='+', type=int, help='subsample sizes', required=True)
    parser.add_argument('-n','--num_unlabeled_docs', type=int, help='size of unlabeled data', required=False)
    parser.add_argument('-x','--num_dev_docs', type=int, help='size of dev data', required=False)
    parser.add_argument('-u','--unlabeled_vocab_size', type=int, help='vocab size of unlabeled data', required=False)
    parser.add_argument('-r','--stopwords', type=str, help='stopword type', required=False)
    args = parser.parse_args()

    if not os.path.exists(args.output_dir):
        os.mkdir(args.output_dir)

    if not os.path.exists(os.path.join(args.output_dir, "full")):
        os.mkdir(os.path.join(args.output_dir, "full"))
    
    if not os.path.exists(os.path.join(args.output_dir, "unlabeled")):
        os.mkdir(os.path.join(args.output_dir, "unlabeled"))

    with open(full_train, 'r') as f:
        labeled_data = pd.read_json(f, lines=True)

    if args.num_dev_docs is not None:
        dev_data = labeled_data.sample(n=args.num_dev_docs)
        labeled_data = labeled_data.drop(dev_data.index)
        out_dir = os.path.join(args.output_dir, "full")
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)
        dev_data.to_json(os.path.join(out_dir, "dev_raw.jsonl"), lines=True, orient='records')
        full_dev = os.path.join(out_dir, "dev_raw.jsonl")

    if args.num_unlabeled_docs is not None:
        unlabeled_data = labeled_data.sample(n=args.num_unlabeled_docs)
        unlabeled_data[args.label] = 0
        labeled_data = labeled_data.drop(unlabeled_data.index)
        out_dir = os.path.join(args.output_dir, "unlabeled")
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)
        unlabeled_data.to_json(os.path.join(out_dir, "train_raw.jsonl"), lines=True, orient='records')

    if not os.path.exists(os.path.join(args.output_dir, "full", "train_raw.jsonl")):
        copyfile(os.path.join(args.data_dir, "train.jsonl"), os.path.join(args.output_dir, "full", "train_raw.jsonl"))

    if not os.path.exists(os.path.join(args.output_dir, "full", "dev_raw.jsonl")) and args.num_dev_docs is None:
        copyfile(os.path.join(args.data_dir, "dev.jsonl"), os.path.join(args.output_dir, "full", "dev_raw.jsonl"))
    
    if not os.path.exists(os.path.join(args.output_dir, "full", "test_raw.jsonl")):
        copyfile(os.path.join(args.data_dir, "test.jsonl"), os.path.join(args.output_dir, "full", "test_raw.jsonl"))

    if not os.path.exists(os.path.join(args.output_dir, "unlabeled", "train_raw.jsonl")):
        copyfile(os.path.join(args.data_dir, "unlabeled.jsonl"), os.path.join(args.output_dir, "unlabeled", "train_raw.jsonl"))

    full_train = os.path.join(args.output_dir, "full", "train_raw.jsonl")
    full_test = os.path.join(args.output_dir, "full", "test_raw.jsonl")
    if args.num_dev_docs is None:
        full_dev = os.path.join(args.output_dir, "full", "dev_raw.jsonl")

    samples = {}
    for size in args.subsamples:
        sample = labeled_data.sample(n=size)
        samples[size] = sample

    preprocess_data(train_infile=full_train,
                    test_infile=full_test,
                    dev_infile=full_dev,
                    output_dir=os.path.join(args.output_dir, "full"),
                    train_prefix="train",
                    test_prefix="test",
                    dev_prefix="dev",
                    min_doc_count=0,
                    max_doc_freq=1.0,
                    vocab_size=args.vocab_size,
                    sample=None,
                    stopwords=args.stopwords,
                    keep_num=False,
                    keep_alphanum=False,
                    strip_html=False,
                    lower=True,
                    min_length=3,
                    label_field=args.label)

    for size, sample in samples.items():
        out_dir = os.path.join(args.output_dir, str(size))
        if not os.path.isdir(out_dir):
            os.mkdir(out_dir)
        sample.to_json(os.path.join(out_dir, "train_raw.jsonl"), lines=True, orient='records')
        preprocess_data(train_infile=os.path.join(out_dir, "train_raw.jsonl"),
                        test_infile=None,
                        dev_infile=None,
                        output_dir=out_dir,
                        train_prefix="train",
                        test_prefix="test",
                        dev_prefix="dev",
                        min_doc_count=0,
                        max_doc_freq=1.0,
                        vocab_size=args.vocab_size,
                        sample=None,
                        stopwords=args.stopwords,
                        keep_num=False,
                        keep_alphanum=False,
                        strip_html=False,
                        lower=True,
                        min_length=3,
                        label_field=args.label)

    preprocess_data(train_infile=os.path.join(args.output_dir, "unlabeled", "train_raw.jsonl"),
                    test_infile=None,
                    dev_infile=None,
                    output_dir=os.path.join(args.output_dir, "unlabeled"),
                    train_prefix="train",
                    test_prefix="test",
                    dev_prefix="dev",
                    min_doc_count=0,
                    max_doc_freq=1.0,
                    vocab_size=args.unlabeled_vocab_size,
                    sample=120000,
                    stopwords=args.stopwords,
                    keep_num=False,
                    keep_alphanum=False,
                    strip_html=False,
                    lower=True,
                    min_length=3,
                    label_field=args.label)

    print("Done!")