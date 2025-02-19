# Multimodality with supernovae 
<p align="center">
    <img src="https://github.com/ThomasHelfer/multimodal-supernovae/blob/main/imgs/logo_cropped.png" alt="no alignment" width="34%" height="auto"/>
</p>

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](https://opensource.org/licenses/MIT)
![Unittest](https://github.com/ThomasHelfer/multimodal-supernovae/actions/workflows/actions.yml/badge.svg)
[![arXiv: 2408.16829](https://img.shields.io/badge/arXiv-2408.16829-b31b1b.svg)](https://arxiv.org/pdf/2408.16829)
[![Hugging Face Dataset: multimodal_supernovae](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Dataset%3A%20multimodal_supernovae-FFD21E)](https://huggingface.co/datasets/thelfer/multimodal_supernovae)

</div>

## Overview
This codebase is dedicated to exploring different self-supervised pretraining methods. We integrate multimodal data from supernovae light curves with images of their host galaxies. Our goal is to leverage diverse data types to improve the prediction and understanding of astronomical phenomena. 

An overview over the the CLIP method and loss [link](https://lilianweng.github.io/posts/2021-05-31-contrastive/) 

All data used in this work is available here: [link](https://huggingface.co/datasets/thelfer/multimodal_supernovae)

Paper associated with code [link](https://arxiv.org/pdf/2408.16829)

Our transformer-based model [Maven](models/clip_noiselesssimpretrain_clipreal) is pretrained on simulated data and finetuned on observations. We compare it with [Maven-lite](models/clip_real) which is directly trained on observations, and a transformer-based supervised [classifcation model](models/lc_3way_f1) and [regression model](models/lc_reg). 

## Installation

### Prerequisites
Before installing, ensure you have the following prerequisites:
- Python 3.8 or higher
- pip package manager

### Steps
1. #### Clone the Repository
   Clone the repository to your local machine and navigate into the directory:
   ```bash
   git clone git@github.com:ThomasHelfer/Multimodal-hackathon-2024.git
   cd Multimodal-hackathon-2024.git
   ```

2. #### Get data
   Unpack the dataset containing supernovae spectra, light curves and host galaxy images:
   ```bash
   git clone https://huggingface.co/datasets/thelfer/multimodal_supernovae
   mv multimodal_supernovae/ZTFBTS* .
   mkdir sim_data && cd sim_data 
   wget https://huggingface.co/datasets/thelfer/multimodal_supernovae/resolve/main/sim_data/ZTF_Pretrain_5Class.hdf5
   ```
  
4. #### Install Required Python Packages
   We recommend to set up an virtual enviorment
   ```bash
   virtualenv dev
   source dev/bin/activate
   ```
   Install all dependencies listed in the requirements.txt file:
   ```bash
   pip install -r requirements.txt 
   ```
5. #### Pretrain on simulated data
   Run the pretrain script
   ```bash
   python pretraining_clip_wandb.py pretrain_config/maven_pretrain_config.yaml 
   ```
6. #### Finetune maven on real data
   Clip finetuning the pretrained model 
   ```bash
   python finetune_clip.py configs/maven_finetune.yaml
   ```
   the config file uses the path of our pre-trained model, to apply this to your model, please change the path 
7. #### Train maven-lite
   Run the script
   ```bash
   python script_wandb.py configs/maven-lite.yaml
   ```
### Setting Up a Hyperparameter Scan with Weights & Biases

1. #### Create a Weights & Biases Account
   Sign up for an account at [Weights & Biases]((https://wandb.ai)) if you haven't already.
2. #### Configure Your Project
   Edit the configuration file to specify your project name. Ensure the name matches the project you create on [wandb.ai](https://wandb.ai). You can define sweep parameters within the [config file](https://github.com/ThomasHelfer/Multimodal-hackathon-2024/blob/main/configs/config_grid.yaml) .
3. #### Choose important parameters
   In the config file you can choose
   ```yaml
   extra_args
     regression: True
   ```
   if true, script_wandb.py performs a regression for redshift.
   Similarly for
   ```yaml
   extra_args
     classification: True
   ```
   if true, script_wandb.py performs a classification.
   if neither are true, it will perform a normal clip pretraining.
   Lastly, for
   ```yaml
   extra_args
     pretrain_lc_path: 'path_to_checkpoint/checkpoint.ckpt'
     freeze_backbone_lc: True
   ```
   preloads a pretrained model in script_wandb.py or allows to restart a run from a checkpoint for retraining_wandb.py
5. #### Run the Sweep Script
   Start the hyperparameter sweep with the following command:
   ```bash
   python script_wandb.py configs/config_grid.yaml 
   ```
   Resume a sweep with the following command:
   ```bash
   python script_wandb.py [sweep_id]
   ```
6. #### API Key Configuration
   The first execution will prompt you for your Weights & Biases API key, which can be found [here]([https://wandb.ai](https://wandb.ai/authorize)https://wandb.ai/authorize). 
 Alternatively, you can set your API key as an environment variable, especially if running on a compute node:
      ```bash
   export WANDB_API_KEY=...
   ```
7. #### View Results
   Monitor and analyze your experiment results on your Weights & Biases project page. [wandb.ai](https://wandb.ai)

### Running a k-fold cross-validation
   We can run a k-fold cross validation by defining the variable 
   ```yaml
    extra_args:
      kfolds: 5 # for strat Crossvaildation
   ```
   as this can take serially very long, one can choose to split your runs for different submission by just choosing certain folds for each submission    
   ```yaml
      foldnumber:
        values: [1,2,3]
   ```

### Calculate performance metrics from models
   To calculate the performance of checkpoint files of models, change the folderpath in the file evaluate_models.py 
   and corresponding name. Then simply calculate metrics by running 
   ```bash
   python evaluate_models.py
   ```

