"""
Contains various util functions for loading and computing embeddings.
"""
import math
import gensim
import numpy as np
from tqdm import tqdm
from typing import *
import scipy.spatial.distance
import matplotlib.pyplot as plt
import evaluation.util
import evaluation.embeddings.util
from evaluation import config


def _random_sentence(vocab: List[str]) -> str:
    """
	Generates a completely random sentence using the local unix dictionary.
	
	Args:
		vocab (List[str]): List of strings which creates our vocabulary.

	Returns:
		sentence: Random sentence.
	"""
    # Determine sentence length.
    n_words = int(np.clip(np.random.lognormal(8, 3), 2, 15))

    # Select words.
    vocab_size = len(vocab)
    idx = np.random.choice(np.arange(0, vocab_size), (n_words,), replace=True)

    # Compose the sentence.
    sentence = ""
    for i in idx:
        sentence += f" {vocab[i]}"

    sentence = evaluation.util.canonicalize(sentence)
    return sentence


def random_sentences(n: int, use_corpus: bool = False) -> List[str]:
    """
	Generates a list of random sentences.
	
	Args:
		n (int): Number of sentences to generate.
		use_corpus (bool): If True, selects sentences from the corpus.
			Note that these are not randomly generated sentences.
	
	Returns:
		sentences: Randomly generated sentences.
	"""
    sentences: List[str] = []

    if use_corpus:
        # Load the corpus.
        paired = evaluation.util.load_paired_json(skip_empty=True)

        # Select subset.
        gids = np.asarray(list(paired.keys()))
        idxs = np.random.choice(np.arange(len(gids)), (n,), replace=False)
        for idx in idxs:
            random_gid = gids[idx]
            sentences.append(paired[random_gid]["gt"])
    else:
        # Load the vocab file.
        with open(config.VOCAB_FQN, "r") as f:
            vocab = [x.strip().lower() for x in f.readlines()]

        # Create `n` sentences.
        for _ in range(n):
            sentences.append(_random_sentence(vocab))

    return sentences


def batch_distance(matrix: np.ndarray) -> np.ndarray:
    """
	Given a matrix of embeddings, where each row is an embedding,
	computes the pairwise similarity of all rows, excluding
	same-row comparisons.
	
	Args:
		matrix (np.ndarray): (N, embedding_size) matrix of embeddings.
	
	Returns:
		dists (np.ndarray): Vector of distances.
	"""
    raise NotImplementedError


def batch_encode(
    embedding_name: str,
    model: Dict[str, np.ndarray],
    keys: Set[str],
    sentences: List[str],
) -> np.ndarray:
    """
	Encodes a List of sentences into multiple embeddings.
	
	Args:
		embedding_name (str): 'word2vec' or 'glove'
		model (Dict[str, np.ndarray]): KeyedVector word2vec model.
		keys (Set[str]): Set of words in the model's vocabulary.
		sentences (List[str]): List of sentences.
	
	Returns:
		np.ndarray: (N, F) embedding matrix.
	"""
    n = len(sentences)
    embeddings = np.zeros((n, config.F[embedding_name]))
    for i in range(n):
        embed = encode_from_dict(embedding_name, model, keys, sentences[i])
        embeddings[i] = embed
    return embeddings


def load_embedding_model(embedding_name: str) -> (Dict, Set[str]):
    """
	Loads an embedding model.
	
	Args:
		embedding_name (str): 'glove' or 'word2vec'
	Returns:
		model: Dictionray of key->np.ndarray embeddings
		keys: Set of strings, corresponding to all words in the vocab.
	"""
    if embedding_name == "word2vec":
        model = gensim.models.KeyedVectors.load_word2vec_format(
            config.WORD2VEC_MODEL_FQN, binary=True
        )
        keys = model.vocab
    elif embedding_name == "glove":
        model = load_glove(config.GLOVE_MODEL_FQN)
        keys = set(model.keys())
    return model, keys


def encode_from_dict(
    embedding_name: str, model: Dict[str, np.ndarray], keys: Set[str], sentence: str,
) -> Optional[np.ndarray]:
    """
	Encodes a sentence using a dictionary-based embedding. That is, either word2vec or Glove.
	A dictionary-based embedding has words as the keys and a numpy array as the value.

	:param embedding_name: Embedding name.
	:param model: Glove or word2vec model (usually a dictionary-like structure).
	:param keys: Set of valid words in the model.
	:param sentence: Sentence as a string.
	:return embedding: Numpy array of the sentence embedding.
	"""
    words = sentence.split(" ")
    # Count the number of words for which we have an embedding.
    count = 0
    for word in words:
        if word in keys:
            count += 1
    if count == 0:
        return None

    # Get embeddings for each word.
    embeddings = np.zeros((count, config.F[embedding_name]), np.float32)
    idx = 0
    for word in words:
        if word in keys:
            embeddings[idx] = model[word]
            idx += 1

    # Mean pooling.
    embedding = embeddings.mean(0)
    return embedding


def load_glove(path: str) -> Dict[str, np.ndarray]:
    """
	Loads the GloVe model.
	
	Args:
		path (str): Full path to the glove model (text file).
	
	Returns:
		Dict[str, np.ndarray]: Glove model with key=word and value=embedding vector.
	"""
    model: Dict[str, np.ndarray] = {}
    with open(path, "r") as f:
        for line in f:
            tokens = line.strip().split(" ")
            word = tokens[0]
            vec = np.array([float(x) for x in tokens[1:]])
            model[word] = vec
    return model


def print_metrics(arr: np.ndarray, text: str):
    """Prints various metrics for an array."""
    if isinstance(arr, list):
        arr = np.asarray(arr)
    print(f"------ {text} ------")
    print(f"Mean: {arr.mean():.2f}")
    print(f"Std: {arr.std():.2f}")
    print(f"Range: {arr.min():.2f} to {arr.max():.2f}")
    print(f"Median: {np.median(arr):.2f}")
    print(f"n: {len(arr)}")
    print(
        f"{arr.mean():.2f} ± {arr.std():.2f} ({np.median(arr):.2f} [{arr.min():.2f}-{arr.max():.2f}]), n: {len(arr)}"
    )


def plot_histogram(
    fqn: str, random_dists: np.ndarray, corpus_dists: np.ndarray, n_bins: int = 30,
):
    """
	Plots a histogram of the random and corpus distances.
	
	Args:
		fqn (str): Where to save the output figure.
		random_dists (np.ndarray): (N,) vector of distances between random sentences.
		corpus_dists (np.ndarray): (N,) vector of distances between corpus sentences.
	"""
    # For histogram to sum to 1, histogram requires integer=1 width bins. Our distances
    # are often very small. Therefore, we need to scale the distances (temporarily) to compute hist.
    random_dists = (random_dists * n_bins).astype(np.int64)
    corpus_dists = (corpus_dists * n_bins).astype(np.int64)

    # Need to manually specify bins otherwise the histogram will not sum to 1.
    min_val = min(random_dists.min(), corpus_dists.min())
    max_val = max(random_dists.max(), corpus_dists.max())
    bins = np.arange(min_val, max_val)

    # Create the histogram.
    _, axes = plt.subplots(1, 1, figsize=(16, 10))
    axes.hist(
        random_dists, bins=bins, density=True, facecolor="g", alpha=0.6, label="Random",
    )
    axes.hist(
        corpus_dists, bins=bins, density=True, facecolor="b", alpha=0.6, label="Corpus",
    )
    axes.set_xlabel("Distance")
    axes.set_ylabel("Probability")
    axes.legend()
    plt.savefig(fqn, dpi=400)


def pairwise_metric(A: np.ndarray, metric: str):
    """Computes the pairwise distance and returns a vector of distances."""
    dists = scipy.spatial.distance.cdist(A, A, metric=metric)
    idx1, idx2 = np.nonzero(
        np.tril(dists)
    )  # Only time dist=0 is if exact same sentence, which we want to discard.
    flat = dists[idx1, idx2]

    # Remove nans, inf, etc.
    clean = []
    for val in flat:
        if math.isnan(val) or val <= 0 or math.isinf(val):
            continue
        else:
            clean.append(val)
    clean = np.asarray(clean)
    return clean


def pairwise_wmd(model, sentences: List[str]) -> np.ndarray:
    """
	Computes pairwise Word Mover Distance (WMD) for a list of strings.
	
	Args:
		model: Gensim model.
		sentences (List[str]): List of sentences.
	
	Returns:
		dists: Numpy array of WMD distances.
	"""
    # WMD requires each sentence as a List of words.
    sentences = [x.split() for x in sentences]
    dists: List[float] = []
    n = len(sentences)
    n_dists = int((n ** 2 - n) / 2)
    pbar = tqdm(total=n_dists)
    for i in range(n):
        for j in range(i + 1, n):
            pbar.update(1)
            d = model.wmdistance(sentences[i], sentences[j])
            if math.isnan(d) or d <= 0 or math.isinf(d):
                continue
            dists.append(d)
    pbar.close()
    dists = np.asarray(dists)
    return dists


def compute_distances(
    model: Dict, keys: Set, sentence1: str, sentence2: str
) -> (float, float):
    """
    Computes EMD and cosine distance.
    
    Args:
        model: Gensim model from:
            >>> import gensim.downloader as api
            >>> model = api.load("word2vec-google-news-300")
        keys: List of words in the model's dictionary
            >>> keys = set(model.vocab)
        sentence1 (str): Sentence 1 to be used for distance computation.
        sentence2 (str): Sentence 2 to be used for distance computation.
    """
    # EMD requires List[str] of words.
    emd = model.wmdistance(sentence1.split(" "), sentence2.split(" "))

    # Exctract embeddings.
    embed1 = encode_from_dict("word2vec", model, keys, sentence1)
    embed2 = encode_from_dict("word2vec", model, keys, sentence2)

    # Cosine distance.
    cosine = None
    if embed1 is not None and embed2 is not None:
        cosine = scipy.spatial.distance.cosine(embed1, embed2)

    return cosine, emd


def is_valid_distance(number: float):
    """Checks if the number is a valid (non inf, nan, etc.) distance."""
    if number is None:
        return False
    if math.isnan(number):
        return False
    if math.isinf(number):
        return False
    if number < 0:
        return False
    return True
