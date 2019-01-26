local VAE_FIELDS = import 'vae_fields.jsonnet';

local NUM_GPUS = 1;
// throttle training data
local THROTTLE = 100;
local SEED = 5;
// add vae embeddings
local ADD_VAE = true;
{
    "dataset_reader": {
        "lazy": false,
        "sample": 200,
        "type": "semisupervised_text_classification_json",
        "tokenizer": {
            "word_splitter": "just_spaces",
        },
        "token_indexers": {
            "tokens": {
                "type": "single_id",
                "namespace": "tokens",
                "lowercase_tokens": true,
            }
        },
        "ignore_labels": false,
        "shift_target": false,
        "sequence_length": 400
    },
    "validation_dataset_reader": {
        "lazy": false,
        "type": "semisupervised_text_classification_json",
        "tokenizer": {
            "word_splitter": "just_spaces",
        },
        "token_indexers": {
            "tokens": {
                "type": "single_id",
                "namespace": "tokens",
                "lowercase_tokens": true,
            }
        },
        "ignore_labels": false,
        "shift_target": false,
        "sequence_length": 400
    },
  "datasets_for_vocab_creation": ["train"],
  "train_data_path": "/home/ubuntu/vae/dump/imdb/train.jsonl",
  "validation_data_path": "/home/ubuntu/vae/dump/imdb/test.jsonl",
    "model": {
        "type": "seq2seq_classifier",
        "text_field_embedder": {
            "token_embedders": {
                "tokens": {
                    "type": "embedding",
                    "embedding_dim": 300,
                    "trainable": true,
                }
            },
        },
        "encoder": {
           "type": "lstm",
           "num_layers": 2,
           "bidirectional": true,
	       "input_size": 300,
           "hidden_size": 128, 
        },
        "aggregations": ["maxpool", "final_state"],
        "output_feedforward": {
            "input_dim": 512,
            "num_layers": 1,
            "hidden_dims": 128,
            "activations": "relu",
            "dropout": 0.5
        },
        "classification_layer": {
            "input_dim": 128,
            "num_layers": 1,
            "hidden_dims": 32,
            "activations": "linear"
        },
        "initializer": [
            [".*linear_layers.*weight", {"type": "xavier_uniform"}],
            [".*linear_layers.*bias", {"type": "zero"}],
            [".*weight_ih.*", {"type": "xavier_uniform"}],
            [".*weight_hh.*", {"type": "orthogonal"}],
            [".*bias_ih.*", {"type": "zero"}],
            [".*bias_hh.*", {"type": "lstm_hidden_bias"}]
        ]
    },
    "iterator": {
        "type": "bucket",
        "sorting_keys": [["tokens", "num_tokens"]],
        "batch_size": 32
    },
    "trainer": {
        "optimizer": {
            "type": "adam",
            "lr": 0.0004
        },
        "validation_metric": "+accuracy",
        "num_serialized_models_to_keep": 2,
        "num_epochs": 75,
        "grad_norm": 10.0,
        "patience": 5,
        "cuda_device": 0,
        "learning_rate_scheduler": {
            "type": "reduce_on_plateau",
            "factor": 0.5,
            "mode": "max",
            "patience": 0
        }
    }
}

