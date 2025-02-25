import os
import pandas as pd
import torch
import pickle as pickle
import numpy as np
import argparse

from transformers import AutoTokenizer, AutoConfig, AutoModelForSequenceClassification
from torch.utils.data import DataLoader
from pprint import pprint

from load_data import *

def inference(models, tokenized_sent, tokenized_tta_sent, device, save_file_name, with_tta=False, model_arc='Electra'):
  dataloader = DataLoader(tokenized_sent, batch_size=40, shuffle=False)    
  tta_dataloader = DataLoader(tokenized_tta_sent, batch_size=40, shuffle=False)
  output_preds = []
  for model in models:
    model.parameters
    model.to(device)
    model.eval()
    output_pred = []
    if with_tta == False:
      for _, data in enumerate(dataloader):
        with torch.no_grad():
          if model_arc == 'Electra':
            outputs = model(
                input_ids=data['input_ids'].to(device),
                attention_mask=data['attention_mask'].to(device),
                token_type_ids=data['token_type_ids'].to(device)
                )
          else:
            outputs = model(
                input_ids=data['input_ids'].to(device),
                attention_mask=data['attention_mask'].to(device)
                )
        logits = outputs[0]
        logits = logits.detach().cpu().numpy()
        output_pred.append(logits)      
      output_preds.append(output_pred)
    else:
      for _, (data, tta_data) in enumerate(zip(dataloader, tta_dataloader)):
        with torch.no_grad():
          outputs = model(
              input_ids=data['input_ids'].to(device),
              attention_mask=data['attention_mask'].to(device),
              token_type_ids=data['token_type_ids'].to(device)
              )
          tta_outputs = model(
            input_ids=tta_data['input_ids'].to(device),
            attention_mask=tta_data['attention_mask'].to(device),
            token_type_ids=tta_data['token_type_ids'].to(device)
            )
        logits = torch.stack((outputs[0], tta_outputs[0])).mean(dim=0)
        logits = logits.detach().cpu().numpy()
        output_pred.append(logits)      
      output_preds.append(output_pred)

  output_preds = np.mean(output_preds, axis=0)
  
  np.save(f'/opt/ml/code/prediction/npy_output/{save_file_name}_kfold.npy', output_preds)

  result = np.argmax(output_preds, axis=-1)
  return np.array(result).flatten()

def load_test_dataset(dataset_dir, tokenizer, model_arc='Electra'):
  test_dataset = load_data(dataset_dir)
  test_label = test_dataset['label'].values
  # tokenizing dataset
  if model_arc == 'Electra':
    tokenized_test = tokenized_dataset(test_dataset, tokenizer)
  else:
    tokenized_test = roberta_tokenized_dataset(test_dataset, tokenizer)
  return tokenized_test, test_label

def main(args):
  """
    주어진 dataset tsv 파일과 같은 형태일 경우 inference 가능한 코드입니다.
  """
  SAVE_FILE_NAME = args.model_dir[21:].replace('/', '_')

  device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
  # load tokenizer
  # TOK_NAME = "bert-base-multilingual-cased"  
  if args.model_arc == 'Electra':
    TOK_NAME = "monologg/koelectra-base-v3-discriminator"
  else:
    TOK_NAME = "xlm-roberta-large"
  # tokenizer = AutoTokenizer.from_pretrained(TOK_NAME)
  tokenizer = AutoTokenizer.from_pretrained(TOK_NAME)

  # load my model
  MODEL_NAMES = [os.path.join(args.model_dir, f'checkpoint-{checkpoint}') for k, checkpoint in enumerate(args.checkpoints) if checkpoint != -1]
  pprint(MODEL_NAMES)  
  # model = BertForSequenceClassification.from_pretrained(args.model_dir)
  models = [AutoModelForSequenceClassification.from_pretrained(model_name) for model_name in MODEL_NAMES]  

  # load test datset
  test_dataset_dir = "/opt/ml/input/data/test/test.tsv"
  test_dataset, test_label = load_test_dataset(test_dataset_dir, tokenizer)
  test_dataset = RE_Dataset(test_dataset ,test_label)

  # Load tta dataset
  tta_dataset_dir = "/opt/ml/input/data/test/tta.tsv"
  tta_dataset, tta_label = load_test_dataset(tta_dataset_dir, tokenizer)
  tta_dataset = RE_Dataset(tta_dataset, tta_label)

  # predict answer
  pred_answer = inference(models, test_dataset, tta_dataset, device, SAVE_FILE_NAME, args.with_tta, args.model_arc)
  # make csv file with predicted answer
  # 아래 directory와 columns의 형태는 지켜주시기 바랍니다.

  output = pd.DataFrame(pred_answer, columns=['pred'])
  output.to_csv(f'./prediction/{SAVE_FILE_NAME}_kfold.csv', index=False)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  
  # model dir
  parser.add_argument('--model_dir', type=str, default="/opt/ml/code/results/xlm-roberta-large")
  parser.add_argument('--checkpoints', type=list, default=[1200, -1, -1, -1, -1])
  parser.add_argument('--with_tta', type=bool, default=False)
  parser.add_argument('--model_arc', type=str, default='Roberta')
  args = parser.parse_args()
  print(args)
  main(args)
  
