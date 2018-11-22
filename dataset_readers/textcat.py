from typing import Dict, List
import logging
import numpy as np
import re
from overrides import overrides
from allennlp.common.file_utils import cached_path
from allennlp.data.dataset_readers.dataset_reader import DatasetReader
from allennlp.data.fields import LabelField, TextField, Field, ListField
from allennlp.data.instance import Instance
from allennlp.data.token_indexers import TokenIndexer, SingleIdTokenIndexer
from allennlp.data.tokenizers import Token
from allennlp.common.checks import ConfigurationError
from allennlp.data.tokenizers import Tokenizer, WordTokenizer
from allennlp.data.tokenizers.word_filter import StopwordFilter

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@DatasetReader.register("textcat")
class TextCatReader(DatasetReader):
    """
    General reader for text classification datasets.

    Reads tokens and their labels in a tsv format.

    ``full`` namespace contains tokenized text with the full vocabulary.

    The output of ``read`` is a list of ``Instance`` s with the fields:
        tokens: ``TextField`` and
        label: ``LabelField``

    Parameters
    ----------
    lazy : ``bool``, optional, (default = ``False``)
        Whether or not instances can be read lazily.
    debug : ``bool``, optional, (default = ``False``)
        Whether or not to run in debug mode, 
        where we just subsample the dataset.
    """
    def __init__(self,
                 lazy: bool = False,
                 debug: bool = False) -> None:
        super().__init__(lazy=lazy)
        self.debug = debug
        self._full_word_tokenizer = WordTokenizer(word_filter=StopwordFilter())
        self._full_token_indexers = {
            "tokens": SingleIdTokenIndexer(namespace="full", lowercase_tokens=True)
        }

    @overrides
    def _read(self, file_path):
        with open(cached_path(file_path), "r") as data_file:
            logger.info("Reading instances from lines in file at: %s", file_path)
            columns = data_file.readline().strip('\n').split('\t')
            if self.debug:
                lines = np.random.choice(data_file.readlines(), 100)
            else:
                lines = data_file.readlines()
            for line in lines:
                if not line:
                    continue
                items = line.strip("\n").split("\t")
                tokens = items[columns.index("tokens")]
                category = items[columns.index("category")]
                instance = self.text_to_instance(tokens=tokens,
                                                 category=category)
                if instance is not None:
                    yield instance


    @overrides
    def text_to_instance(self, tokens: List[str], category: str = None) -> Instance:  # type: ignore
        """
        We take `pre-tokenized` input here, because we don't have a tokenizer in this class.

        Parameters
        ----------
        tokens : ``List[str]``, required.
            The tokens in a given sentence.
        category ``str``, optional, (default = None).
            The category for this sentence.

        Returns
        -------
        An ``Instance`` containing the following fields:
            tokens : ``TextField``
                The tokens in the sentence or phrase.
            label : ``LabelField``
                The category label of the sentence or phrase.
        """
        # pylint: disable=arguments-differ
        fields: Dict[str, Field] = {}
        full_tokens = self._full_word_tokenizer.tokenize(tokens)
        if not full_tokens:
            return None
        fields['tokens'] = TextField(full_tokens,
                                     self._full_token_indexers)
        if category is not None:
            if category in ('NA', 'None'):
                category = -1
            fields['label'] = LabelField(category)
            
        return Instance(fields)
