import os
from typing import List, Optional
from pytorch_lightning import LightningModule, Trainer
from pytorch_lightning.callbacks import Callback
import torch
import numpy as np
from torch.utils.data import DataLoader
from typing import Tuple, List, Dict, Any
from matplotlib import pyplot as plt
from ruamel.yaml import YAML
from sklearn.linear_model import LinearRegression
from sklearn.svm import LinearSVC
from sklearn.neighbors import KNeighborsRegressor, KNeighborsClassifier
from sklearn.metrics import (
    f1_score,
    precision_score,
    accuracy_score,
    recall_score,
    balanced_accuracy_score,
)
from torch.nn import Module
import pandas as pd
from sklearn.metrics import confusion_matrix
import seaborn as sns
import matplotlib.ticker as ticker


def filter_files(filenames_avail, filenames_to_filter, data_to_filter=None):
    """
    Function to filter filenames and data based on the filenames_avail

    Args:
    filenames_avail (list): List of filenames available
    filenames_to_filter (list): List of filenames to filter
    data_to_filter (List[np.ndarray]): Data to filter based on filenames_to_filter

    Returns:
    inds_filt (np.ndarray): Indices of filtered filenames in filenames_to_filter
    filenames_to_filter (list): List of filtered filenames
    data_to_filter (np.ndarray): Filtered data
    """
    # Check which each filenames_to_filter are available in filenames_avail
    inds_filt = np.isin(filenames_to_filter, filenames_avail)
    if data_to_filter:
        for i in range(len(data_to_filter)):
            data_to_filter[i] = data_to_filter[i][inds_filt]

    filenames_to_filter = np.array(filenames_to_filter)[inds_filt]

    return inds_filt, filenames_to_filter, data_to_filter


def find_indices_in_arrays(st1, st2):
    """
    Find indices of where elements of st1 appear in st2 and indices in st1 of those elements.

    Parameters:
    - st1 (list or array): The list of strings to find in st2.
    - st2 (list or array): The list of strings to search within.

    Returns:
    - tuple of two lists:
        - The first list contains indices indicating where each element of st1 is found in st2.
        - The second list contains the indices in st1 for elements that were found in st2.
    """
    indices_in_st2 = []
    indices_in_st1 = []
    for idx, item in enumerate(st1):
        try:
            index_in_st2 = st2.index(item)  # Find the index of item in st2
            indices_in_st2.append(index_in_st2)
            indices_in_st1.append(idx)
        except ValueError:
            # Item not found in st2, optionally handle it
            continue  # Simply skip if not found
    return indices_in_st2, indices_in_st1


def get_savedir(args) -> str:
    """
    Return config dict and path to save new plots and models based on
    whether to continue from checkpoint or not; dump config file in savedir path

    Args:
    args: argparse.ArgumentParser object

    Returns:
    str: path to save new plots and models
    cfg: dict: configuration dictionary
    """
    # Create directory to save new plots and checkpoints
    import os

    if not os.path.exists("analysis"):
        os.makedirs("analysis")
        os.makedirs("analysis/runs")
    if not os.path.exists("analysis/runs"):
        os.makedirs("analysis/runs")

    # save in checkpoint directory if resuming from checkpoint
    # else save in numbered directory if not given runname
    if args.ckpt_path:
        cfg = YAML(typ="safe").load(
            open(os.path.join(os.path.dirname(args.ckpt_path), "config.yaml"))
        )
        save_dir = os.path.join(os.path.dirname(args.ckpt_path), "resume/")
        os.makedirs(save_dir, exist_ok=True)
    else:
        yaml = YAML(typ="rt")
        cfg = yaml.load(open(args.config_path))
        if args.runname:
            save_dir = f"./analysis/runs/{args.runname}/"
        else:
            dirlist = [
                int(item)
                for item in os.listdir("./analysis/runs/")
                if os.path.isdir(os.path.join("./analysis/runs/", item))
                and item.isnumeric()
            ]
            dirname = str(max(dirlist) + 1) if len(dirlist) > 0 else "0"
            save_dir = os.path.join("./analysis/runs/", dirname)

        os.makedirs(save_dir, exist_ok=True)
        with open(os.path.join(save_dir, "config.yaml"), "w") as outfile:
            yaml.dump(cfg, outfile)

    return save_dir, cfg


def set_seed(seed: int = 0) -> None:
    """
    set seed so that results are fully reproducible
    """
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)

    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    os.environ["PYTHONHASHSEED"] = str(seed)
    print(f"Random seed: {seed}")


def get_valid_dir(data_dirs: List[str]) -> str:
    """
    Returns the first valid directory in the list of directories.

    Args:
    data_dirs (List[str]): A list of directory paths to check.

    Returns:
    str: The first valid directory path found in the list.

    Raises:
    ValueError: If no valid directory is found in the list.
    """
    for data_dir in data_dirs:
        if os.path.isdir(data_dir):
            return data_dir
    raise ValueError("No valid data directory found")


class LossTrackingCallback(Callback):
    def __init__(self):
        self.train_loss_history = []
        self.val_loss_history = []
        self.epoch_train_loss = []
        self.auc_val_history = []
        self.R2_val_history = []
        self.R2_train_history = []

    def on_train_batch_end(self, trainer, pl_module, outputs, batch, batch_idx):
        # Accumulate training loss for each batch
        loss = outputs["loss"] if isinstance(outputs, dict) else outputs
        self.epoch_train_loss.append(loss.detach().item())

    def on_train_epoch_end(self, trainer, pl_module):
        # Append average training loss after each epoch
        epoch_loss = sum(self.epoch_train_loss) / len(self.epoch_train_loss)
        self.train_loss_history.append(epoch_loss)
        self.R2_train_history.append(trainer.callback_metrics.get("R2_train"))
        # Reset the list for the next epoch
        self.epoch_train_loss = []

    def on_validation_epoch_end(self, trainer, pl_module):
        # Append validation loss after each validation epoch
        val_loss = trainer.callback_metrics.get("val_loss")
        if val_loss is not None:
            self.val_loss_history.append(val_loss.detach().item())

    def on_validation_end(self, trainer: Trainer, pl_module: LightningModule) -> None:
        auc_val = trainer.callback_metrics.get("AUC_val")
        auc_val1 = trainer.callback_metrics.get("AUC_val1")
        self.R2_val_history.append(trainer.callback_metrics.get("R2_val"))
        if auc_val or auc_val1:
            if auc_val is None:
                auc_val = (
                    sum(
                        [
                            trainer.callback_metrics.get(f"AUC_val{i}").detach().item()
                            for i in range(1, 4)
                        ]
                    )
                    / 3
                )
            else:
                auc_val = auc_val.detach().item()
            self.auc_val_history.append(auc_val)


def plot_loss_history(train_loss_history, val_loss_history, path_base="./"):
    """
    Plots the training and validation loss histories.

    Args:
    train_loss_history (list): A list of training loss values.
    val_loss_history (list): A list of validation loss values.
    """
    # Create a figure and a set of subplots
    plt.figure(figsize=(10, 6))

    # Plot training loss
    plt.plot(
        train_loss_history,
        label="Training Loss",
        color="blue",
        linestyle="-",
        marker="o",
    )

    # Plot validation loss
    plt.plot(
        val_loss_history,
        label="Validation Loss",
        color="red",
        linestyle="-",
        marker="x",
    )

    # Adding title and labels
    plt.title("Training and Validation Loss Over Epochs")
    plt.xlabel("Epochs")
    plt.ylabel("Loss")

    # Adding a legend
    plt.legend()

    # Show grid
    plt.grid(True)

    # Show the plot
    plt.savefig(os.path.join(path_base, "loss_history.png"))


def cosine_similarity(a, b, temperature=1):
    """
    Compute cosine similarity between two tensors.

    Args:
    a (torch.Tensor): First tensor.
    b (torch.Tensor): Second tensor.
    temperature (float): Temperature parameter for scaling the cosine similarity; default is 1.

    Returns:
    torch.Tensor: Cosine similarity between the two tensors.
    """
    a_norm = a / a.norm(dim=-1, keepdim=True)
    b_norm = b / b.norm(dim=-1, keepdim=True)

    logits = a_norm @ b_norm.T * temperature
    return logits.squeeze()


def get_embs(
    clip_model: torch.nn.Module,
    dataloader: DataLoader,
    combinations: List[str],
    ret_combs: bool = False,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Computes and concatenates embeddings for different data modalities (images, light curves, spectra)
    from a DataLoader using a specified model. This function allows selection of modalities via a list of combinations.

    Args:
        clip_model (torch.nn.Module): The model used for generating embeddings. It should have methods
                                      to compute embeddings for the specified modalities.
        dataloader (DataLoader): DataLoader that provides batches of data. Each batch should include data
                                 for images, magnitudes, times, and masks for light curves and spectral data.
        combinations (List[str]): List of strings specifying which data modalities to compute embeddings for.
                                  Possible options include 'host_galaxy' for images, 'lightcurve' for light curves,
                                  and 'spectral' for spectral data.
        ret_combs (bool, optional): If True, returns a tuple of the embeddings and the names of the modalities
                                    processed. Defaults to False.

    Returns:
        Tuple[torch.Tensor, ...] or Tuple[List[torch.Tensor], np.ndarray]:
            - If ret_combs is False, returns a list of torch.Tensor, each tensor represents concatenated embeddings
              for each modality specified in combinations.
            - If ret_combs is True, returns a tuple containing the list of concatenated embeddings and an array of
              modality names that were included in the combinations and processed.
    """

    clip_model.eval()
    # getting device of model
    device = next(clip_model.parameters()).device

    embs_list = [[] for i in range(len(combinations))]

    # gives combination names corresponding each emb in embs_list
    combs_all = ["host_galaxy", "lightcurve", "spectral", "meta"]
    combs = np.array(combs_all)[np.isin(combs_all, combinations)]

    # Iterate through the DataLoader
    for batch in dataloader:
        (
            x_img,
            x_lc,
            t_lc,
            mask_lc,
            x_sp,
            t_sp,
            mask_sp,
            redshift,
            classification,
        ) = batch
        if "host_galaxy" in combinations:
            x_img = x_img.to(device)
        if "lightcurve" in combinations:
            x_lc = x_lc.to(device)
            t_lc = t_lc.to(device)
            mask_lc = mask_lc.to(device)
        if "spectral" in combinations:
            x_sp = x_sp.to(device)
            t_sp = t_sp.to(device)
            mask_sp = mask_sp.to(device)

        # Compute embeddings and detach from the computation graph
        with torch.no_grad():
            x = []
            if "host_galaxy" in combinations:
                x.append(clip_model.image_embeddings_with_projection(x_img))
            if "lightcurve" in combinations:
                x.append(
                    clip_model.lightcurve_embeddings_with_projection(
                        x_lc, t_lc, mask_lc
                    )
                )
            if "spectral" in combinations:
                x.append(
                    clip_model.spectral_embeddings_with_projection(x_sp, t_sp, mask_sp)
                )
            if "meta" in combinations:
                # half of the input is the class embedding, the other half is the redshift
                x_meta = torch.concat(
                    [
                        clip_model.class_emb(classification.to(device)).to(device),
                        redshift.unsqueeze(1)
                        .repeat(1, clip_model.len_meta_input // 2)
                        .to(device),
                    ],
                    dim=-1,
                ).to(device)
                x_meta = clip_model.meta_encoder(x_meta)
                x.append(x_meta)

        # Append the results to the lists
        for i in range(len(x)):
            embs_list[i].append(x[i].detach())

    # Concatenate all embeddings into single tensors
    for i in range(len(embs_list)):
        embs_list[i] = torch.cat(embs_list[i], dim=0)

    if not ret_combs:
        return embs_list
    return embs_list, combs


def get_ROC_data(
    embs1: torch.Tensor, embs2: torch.Tensor
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate ROC-like data by evaluating the cosine similarity between two sets of embeddings.

    Args:
    embs1 (torch.Tensor): Tensor of first set of embeddings.
    embs2 (torch.Tensor): Tensor of second set of embeddings.

    Returns:
    Tuple[np.ndarray, np.ndarray]: A tuple containing an array of thresholds and an array of the fraction of correct predictions at each threshold.
    """
    thresholds = np.linspace(0, 1, 100)
    imgs = []

    # Iterate through image embeddings and calculate cosine similarity with curve embeddings
    for idx, emb_src in enumerate(embs2):
        cos_sim = cosine_similarity(embs1, emb_src)
        idx_sorted = torch.argsort(cos_sim, descending=True)

        # Calculate the number of correct predictions for each threshold
        num_right = [
            idx in idx_sorted[: int(threshold * len(idx_sorted))]
            for threshold in thresholds
        ]
        imgs.append(num_right)

    # Calculate the fraction of correct predictions at each threshold
    fraction_correct = np.sum(imgs, axis=0) / len(embs2)

    return thresholds, fraction_correct


def get_AUC(
    embs1: torch.Tensor,
    embs2: torch.Tensor,
) -> Tuple[float, float]:
    """
    Calculate the area under the ROC curve for training and validation datasets.
    Args:
    embs1 (torch.Tensor): Embeddings for first modality.
    embs2 (torch.Tensor): Embeddings for second modality.
    """
    thresholds, fraction_correct = get_ROC_data(embs1, embs2)
    auc = np.trapz(fraction_correct, thresholds)
    return auc


def plot_ROC_curves(
    embs_train: List[torch.Tensor],
    embs_val: List[torch.Tensor],
    combinations: List[str],
    path_base: str = "./",
) -> None:
    """
    Plots ROC-like curves for training and validation datasets based on embeddings.

    Args:
    embs_train (List[torch.Tensor]): List of embeddings for training data.
    embs_val (List[torch.Tensor]): List of embeddings for validation data.
    combinations (List[str]): List of combinations of modalities to use for embeddings.
    path_base (str) : path to save the plot
    """

    combinations = sorted(combinations)

    fractions_train, fractions_val, labels = [], [], []
    for i in range(len(embs_train) - 1):
        for j in range(i + 1, len(embs_train)):
            thresholds, fraction_correct_train = get_ROC_data(
                embs_train[i], embs_train[j]
            )
            thresholds, fraction_correct_val = get_ROC_data(embs_val[i], embs_val[j])
            fractions_train.append(fraction_correct_train)
            fractions_val.append(fraction_correct_val)
            labels.append(f"{combinations[i]} and {combinations[j]}")

    # Set overall figure size and title
    plt.figure(figsize=(12, 6))
    plt.suptitle("Fraction of Correct Predictions vs. Threshold")

    # Plot for validation data
    plt.subplot(1, 2, 1)
    for i, f_val in enumerate(fractions_val):
        plt.plot(thresholds, f_val, lw=2, label=labels[i])
    plt.plot(thresholds, thresholds, linestyle="--", color="gray", label="Random")
    plt.title("Validation Data")
    plt.xlabel("Threshold")
    plt.ylabel("Fraction Correct")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.7)

    # Plot for training data
    plt.subplot(1, 2, 2)
    for i, f_train in enumerate(fractions_train):
        plt.plot(thresholds, f_train, lw=2, label=labels[i])
    plt.plot(thresholds, thresholds, linestyle="--", color="gray", label="Random")
    plt.title("Training Data")
    plt.xlabel("Threshold")
    plt.ylabel("Fraction Correct")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.7)

    # Adjust layout to prevent overlapping
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(os.path.join(path_base, "ROC_curves.png"))


def get_linear_predictions(
    X: torch.Tensor,
    Y: torch.Tensor,
    X_val: Optional[torch.Tensor] = None,
    Y_val: Optional[torch.Tensor] = None,
    task: str = "regression",
) -> torch.Tensor:
    """
    Calculate predictions using a linear regression model (or a linear-kernel SVM, for classification).

    Parameters:
    X (torch.Tensor): The input features for training.
    Y (torch.Tensor): The target values for training.
    X_val (Optional[torch.Tensor]): The input features for validation (default is None).
    Y_val (Optional[torch.Tensor]): The target values for validation (default is None).
    task (str): The downstream task ('regression' or 'classification').

    Returns:
    torch.Tensor: The predictions of the model trained on training data or on validation data if provided.
    """
    # Ensure Y is 2D (necessary for sklearn)
    if len(Y.shape) == 1:
        Y = Y[:, np.newaxis]

    # Convert tensors to numpy
    X = X.cpu().detach().numpy()
    if X_val is not None:
        X_val = X_val.cpu().detach().numpy()

    # fit the model
    if task.lower() == "regression":
        model = LinearRegression().fit(X, Y)
    elif task.lower() == "classification":
        model = LinearSVC().fit(X, Y)
    else:
        raise ValueError("Invalid task")

    # If validation data is provided, make predictions on that, otherwise on training data
    if X_val is not None and Y_val is not None:
        predictions = model.predict(X_val)
    else:
        predictions = model.predict(X)

    # Convert numpy array back to PyTorch tensor
    predictions_tensor = torch.from_numpy(predictions).flatten()

    return predictions_tensor


def get_knn_predictions(
    X: torch.Tensor,
    Y: torch.Tensor,
    X_val: Optional[torch.Tensor] = None,
    Y_val: Optional[torch.Tensor] = None,
    k: int = 5,
    task: str = "regression",
) -> torch.Tensor:
    """
    Calculate predictions using a k-nearest neighbors regression model.

    Parameters:
    X (torch.Tensor): The input features for training.
    Y (torch.Tensor): The target values for training.
    X_val (Optional[torch.Tensor]): The input features for validation (default is None).
    Y_val (Optional[torch.Tensor]): The target values for validation (default is None).
    k (int): The number of neighbors to use for k-nearest neighbors.
    task (str): The downstream task ('regression' or 'classification').

    Returns:
    torch.Tensor: The 1D predictions of the model trained on training data or on validation data if provided.
    """
    # Ensure Y is 2D (necessary for sklearn)
    if len(Y.shape) == 1:
        Y = Y[:, np.newaxis]

    # Convert tensors to numpy
    X = X.cpu().detach().numpy()
    if X_val is not None:
        X_val = X_val.cpu().detach().numpy()

    # fit the model
    if task.lower() == "regression":
        model = KNeighborsRegressor(n_neighbors=k).fit(X, Y)
    elif task.lower() == "classification":
        model = KNeighborsClassifier(n_neighbors=k).fit(X, Y)
    else:
        raise ValueError("Invalid task")

    # If validation data is provided, make predictions on that, otherwise on training data
    if X_val is not None and Y_val is not None:
        predictions = model.predict(X_val)
    else:
        predictions = model.predict(X)

    # Convert numpy array back to PyTorch tensor and flatten to 1D
    predictions_tensor = torch.from_numpy(predictions).flatten()

    return predictions_tensor


def is_subset(subset: List[str], superset: List[str]) -> bool:
    """
    Check if a list of filenames (subset) is completely contained within another list of filenames (superset).

    Args:
    subset (List[str]): A list of filenames to be checked if they are contained within the superset.
    superset (List[str]): A list of filenames that is expected to contain all elements of the subset.

    Returns:
    bool: Returns True if all elements in the subset are found in the superset, otherwise False.
    """
    # Convert lists to sets for efficient subset checking
    subset_set = set(subset)
    superset_set = set(superset)

    # Check if subset is a subset of superset
    return subset_set.issubset(superset_set)


def process_data_loader(
    loader: DataLoader,
    regression: bool,
    classification: bool,
    device: str,
    model: Module,
    combinations: List[str],
) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
    """
    Processes batches from a DataLoader to generate model predictions and true labels for regression or classification.

    Args:
        loader (DataLoader): The DataLoader from which data batches are loaded.
        regression (bool): Indicates whether the processing is for regression tasks.
        classification (bool): Indicates whether the processing is for classification tasks.
        device (str): The device (e.g., 'cuda', 'cpu') to which tensors are sent for model computation.
        model (Module): The neural network model that processes the input data.
        combinations (List[str]): Specifies which types of data (e.g., 'host_galaxy', 'lightcurve', 'spectral') are included in the input batches.

    Returns:
        Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]: A tuple containing:
            - The true values for the regression or classification targets.
            - The true labels for classification if available.
            - The predicted values from the model if regression is true, otherwise None.
    """
    y_true_val = []
    y_pred_val = []
    y_true_val_label = []
    lc_datas = []
    time_lc_datas = []
    masked_lc_datas = []

    for batch in loader:
        # Send them all existing tensors to the device
        (
            x_img,
            x_lc,
            t_lc,
            mask_lc,
            x_sp,
            t_sp,
            mask_sp,
            redshift,
            labels,
        ) = batch
        # tracking lc data for later checks
        lc_datas.append(x_lc)
        time_lc_datas.append(t_lc)
        masked_lc_datas.append(mask_lc)

        if regression or classification:
            if "host_galaxy" in combinations:
                x_img = x_img.to(device)
            if "lightcurve" in combinations:
                x_lc = x_lc.to(device)
                t_lc = t_lc.to(device)
                mask_lc = mask_lc.to(device)
            if "spectral" in combinations:
                x_sp = x_sp.to(device)
                t_sp = t_sp.to(device)
                mask_sp = mask_sp.to(device)
            x = model(x_img, x_lc, t_lc, mask_lc, x_sp, t_sp, mask_sp)
            if regression:
                y_pred_val.append(x.detach().cpu().flatten())
            elif classification:
                _, predicted_classes = torch.max(x, dim=1)
                y_pred_val.append(predicted_classes.detach().cpu().flatten())

        y_true_val.append(redshift)
        y_true_val_label.append(labels)

    y_true = torch.cat(y_true_val, dim=0)
    y_true_val_label = torch.cat(y_true_val_label, dim=0)
    if regression or classification:
        y_pred_val = torch.cat(y_pred_val, dim=0)
    if len(lc_datas) > 0 and lc_datas[0] is not None:
        x_lc = torch.cat(lc_datas, dim=0)
        t_lc = torch.cat(time_lc_datas, dim=0)
        mask_lc = torch.cat(masked_lc_datas, dim=0)
        lc_data = {"x_lc": x_lc, "t_lc": t_lc, "mask_lc": mask_lc}
    else:
        lc_data = None
    return y_true, y_true_val_label, y_pred_val, lc_data


def print_metrics_in_latex(
    metrics_list: List[Dict[str, float]], drop=None, sort=None
) -> None:
    """
    Generates LaTeX code from a list of metric dictionaries and prints it.

    This function takes a list of dictionaries where each dictionary represents
    performance metrics for a particular model and data combination. It converts
    this list into a DataFrame, formats numerical values to three decimal places,
    and converts the DataFrame to LaTeX format which it then prints.

    Args:
        metrics_list (List[Dict[str, float]]): A list of dictionaries with keys as metric names
                                               and values as their respective numerical values.
        drop: List of columns to drop from the table
        sort: string of column to sort from the table


    Output:
        None: This function directly prints the LaTeX formatted table to the console.
    """
    """
    Generates a LaTeX table from a list of dictionaries containing model metrics,
    formatting the metrics as mean ± standard deviation for each combination and model.
    
    Parameters:
        data (list of dicts): Each dictionary should contain metrics and descriptors such as Model, Combination, and id.

    Returns:
        str: A LaTeX formatted table as a string.
    """
    # Convert the list of dictionaries to a DataFrame
    df = pd.DataFrame(metrics_list)

    # Select numeric columns
    numeric_cols = df.select_dtypes(include=[float]).columns
    # Ensure that no more than 4 numeric columns are in one table
    max_cols_per_table = 4

    # Calculate mean and standard deviation
    grouped_df = df.groupby(["id", "Model", "Combination"])[numeric_cols]
    mean_df = grouped_df.mean()
    std_df = grouped_df.std()

    # Generate tables
    num_tables = (
        len(numeric_cols) + max_cols_per_table - 1
    ) // max_cols_per_table  # Calculate how many tables are needed
    tables = []

    for i in range(num_tables):
        # Select subset of columns for the current table
        cols_subset = numeric_cols[
            i * max_cols_per_table : (i + 1) * max_cols_per_table
        ]
        summary_df = mean_df[cols_subset].copy()

        # Format 'mean ± std' for each metric in the subset
        for col in cols_subset:
            summary_df[col] = (
                mean_df[col].apply("{:.3f}".format)
                + " ± "
                + std_df[col].apply("{:.3f}".format)
            )

        # Reset the index and drop 'id'
        summary_df.reset_index(inplace=True)
        summary_df.drop(columns="id", inplace=True)
        if drop is not None:
            summary_df.drop(columns=drop, inplace=True)
        if sort is not None:
            if sort in summary_df.columns:
                summary_df.sort_values(by=sort, inplace=True, ascending=False)

        # Generate LaTeX table for the current subset of columns
        latex_table = summary_df.to_latex(
            escape=False,
            column_format="|c" * (len(summary_df.columns)) + "|",
            index=False,
            header=True,
        )
        tables.append(latex_table)

        print(latex_table)


def get_checkpoint_paths(
    root_dir: str, name: str, id: int
) -> Tuple[List[str], List[str], List[int]]:
    """
    Traverse the directory structure starting from the specified root directory,
    and find the checkpoint file (.ckpt) with the smallest epoch number in each sweep.

    Parameters:
        root_dir (str): The root directory containing different sweep directories.

    Returns:
        List[str]: A list with the paths to the checkpoint file with the smallest epoch number.
        List[str]:
    """
    # Dictionary to hold the paths of the smallest epoch checkpoint files
    ckpt_paths = []

    # Walk through the directory structure
    for dirpath, dirnames, filenames in os.walk(root_dir):
        smallest_epoch = float("inf")
        path_of_smallest = None

        # Filter and process only the checkpoint files
        for filename in filenames:
            if filename.endswith(".ckpt"):
                # Extract epoch number from the filename
                try:
                    epoch = int(filename.split("=")[1].split("-")[0])
                except (IndexError, ValueError):
                    continue

                # Update if the current file has a smaller epoch number
                if epoch < smallest_epoch:
                    smallest_epoch = epoch
                    path_of_smallest = os.path.join(dirpath, filename)

        # Store the path of the checkpoint file with the smallest epoch number for each sweep
        if path_of_smallest:
            ckpt_paths.append(path_of_smallest)

    return ckpt_paths, [name] * len(ckpt_paths), [id] * len(ckpt_paths)


def calculate_metrics(
    y_true: torch.Tensor,
    y_true_label: torch.Tensor,
    y_pred: torch.Tensor,
    lc_data: List[Tuple[torch.Tensor, torch.Tensor, torch.Tensor]],
    label: str,
    combination: str,
    id: int,
    task: str = "regression",
) -> dict:
    """
    Calculates performance metrics (for both classification and redshift estimation) to assess the accuracy of predictions against true values.

    Parameters:
    - y_true (torch.Tensor): The true values against which predictions are evaluated.
    - y_pred (torch.Tensor): The predicted values to be evaluated.
    - lc_data (List[Tuple[torch.Tensor, torch.Tensor, torch.Tensor]]): List of tuples containing light curve data (x_lc, t_lc, mask_lc).
    - label (str): Label describing the model or configuration being evaluated.
    - combination (str): Description of the data or feature combination used for the model.
    - id (int): A unique indentifier to distiguish different k-fold runs
    - task (str): the downstream task being done; can be 'redshift' or 'classification'.

    Returns:
    - dict: A dictionary containing the calculated metrics. Each key describes the metric.
            - 'Model': The label of the model or configuration.
            - 'Combination': Description of the feature or data combination.
         For redshift regression:
            - 'L1': The L1 norm (mean absolute error) of the prediction error.
            - 'L2': The L2 norm (root mean squared error) of the prediction error.
            - 'R2': The coefficient of determination of the prediction error.
            - 'OLF': The outlier fraction of the prediction error.
        For 3- or 5-way classification:
            - 'micro-f1': The micro-averaged f1-score (NOT balanced across classes).
            - 'micro-precision': The micro-averaged precision (true positives / (true positives + false positives), NOT balanced across classes).
            - 'micro-recall': The micro-averaged precision (true positives / (true positives + false negatives), NOT balanced across classes).
            - 'micro-acc': The micro-averaged accuracy (averaged across all points, NOT balanced across classes).

            - 'macro-f1': The macro-averaged f1-score (balanced across classes).
            - 'macro-precision': The macro-averaged precision (true positives / (true positives + false positives), balanced across classes).
            - 'macro-recall': The macro-averaged precision (true positives / (true positives + false negatives), balanced across classes).
            - 'macro-acc': The macro-averaged accuracy (balanced across classes).
    """
    if task == "regression":
        # Calculate L1 and L2 norms for the predictions
        l1 = torch.mean(torch.abs(y_true - y_pred)).item()
        l2 = torch.sqrt(torch.mean((y_true - y_pred) ** 2)).item()
        R2 = (
            1
            - (
                torch.sum((y_true - y_pred) ** 2)
                / torch.sum((y_true - torch.mean(y_true)) ** 2)
            ).item()
        )

        # Calculate the residuals
        delta_z = y_true - y_pred

        # Outliers based on a fixed threshold
        outliers = torch.abs(delta_z) / (1.0 + y_true) > 0.15
        non_outliers = ~outliers

        # calulate the fraction of outliers
        OLF = torch.mean(outliers.float()).item()

        # Compile the results into a metrics dictionary
        metrics = {
            "Model": label,
            "Combination": combination,
            "L1": l1,
            "L2": l2,
            "R2": R2,
            "OLF": OLF,
            "id": id,
        }

    elif task == "classification":
        """
        # Create folder
        if not os.path.exists(f"confusion_plots"):
            os.makedirs(f"confusion_plots")
        # Create the confusion matrix
        cm = confusion_matrix(y_true_label, y_pred)

        # Normalize the confusion matrix
        cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

        # Plotting using seaborn
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm_normalized, annot=True, fmt='.2f', cmap='Blues')
        plt.xlabel('Predicted Label')
        plt.ylabel('True Label')
        plt.title('Normalized Confusion Matrix')
        plt.savefig(f'confusion_plots/{label.replace(" ", "")}_{combination.replace(" ", "")}_fold{id}_confusion_matrix.png')
        print(f'confusion_plots/{label.replace(" ", "")}_{combination.replace(" ", "")}_fold{id}_confusion_matrix.png')
        plt.close()
        """

        y_true_label = y_true_label.cpu().numpy()
        y_pred = y_pred.cpu().numpy()
        y_pred_idxs = y_pred

        # micro f1-score
        micF1 = f1_score(y_true_label, y_pred_idxs, average="micro")

        # micro precision
        micPrec = precision_score(y_true_label, y_pred, average="micro")

        # micro recall
        micRec = recall_score(y_true_label, y_pred_idxs, average="micro")

        # micro accuracy
        # y_pred needs to be array of predicted class labels
        micAcc = accuracy_score(y_true_label, y_pred_idxs, normalize=True)

        # macro f1-score
        macF1 = f1_score(y_true_label, y_pred_idxs, average="macro")

        # macro precision
        macPrec = precision_score(y_true_label, y_pred, average="macro")

        # macro recall
        macRec = recall_score(y_true_label, y_pred_idxs, average="macro")

        # macro accuracy
        # y_pred needs to be array of predicted class labels
        macAcc = balanced_accuracy_score(y_true_label, y_pred_idxs)

        # Compile the results into a metrics dictionary
        metrics = {
            "Model": label,
            "Combination": combination,
            "mic-f1": micF1,
            "mic-p": micPrec,
            "mic-r": micRec,
            "mic-acc": micAcc,
            "mac-f1": macF1,
            "mac-p": macPrec,
            "mac-r": macRec,
            "mac-acc": macAcc,
            "id": id,
        }

    else:
        raise ValueError(
            "Could not understand the task! Please set task to 'redshift' or 'classification'."
        )
    results = {
        "Model": label,
        "Combination": combination,
        "id": id,
        "y_pred": y_pred,
        "y_true": y_true,
        "y_true_label": y_true_label,
        "lc_data": lc_data,
    }
    return metrics, results


def mergekfold_results(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Processes a list of classification results by grouping and concatenating the prediction, label arrays, and lc_data.

    Each result entry should contain 'Model', 'Combination', 'id', 'y_pred', 'y_true_label', and 'lc_data' keys.

    Args:
        results (List[Dict[str, Any]]): A list of dictionaries, each containing classification data.

    Returns:
        pd.DataFrame: A DataFrame with concatenated results grouped by 'Model', 'Combination', and 'id'.
    """

    # Convert the list of dictionaries to a DataFrame
    df = pd.DataFrame(results)

    # Create a dictionary to hold the concatenated results
    concatenated_results = {
        "Model": [],
        "Combination": [],
        "id": [],
        "y_pred": [],
        "y_true": [],
        "y_true_label": [],
        "lc_data": [],
    }

    # Group by 'Model', 'Combination', 'id'
    grouped = df.groupby(["Model", "Combination", "id"])

    # Iterate through each group and concatenate the results
    for (model, combination, id_), group in grouped:
        concatenated_results["Model"].append(model)
        concatenated_results["Combination"].append(combination)
        concatenated_results["id"].append(id_)

        concatenated_results["y_pred"].append(
            np.concatenate(group["y_pred"].dropna().values)
        )
        concatenated_results["y_true"].append(
            np.concatenate(group["y_true"].dropna().values)
        )
        concatenated_results["y_true_label"].append(
            np.concatenate(group["y_true_label"].dropna().values)
        )

        # Concatenate lc_data if it's not None
        if group["lc_data"].notna().any():
            lc_data_concat = {
                key: np.concatenate([d[key] for d in group["lc_data"].dropna().values])
                for key in group["lc_data"].dropna().values[0].keys()
            }
        else:
            lc_data_concat = None
        concatenated_results["lc_data"].append(lc_data_concat)

    # Convert the concatenated results to a DataFrame
    concatenated_df = pd.DataFrame(concatenated_results)

    return concatenated_df


def save_normalized_conf_matrices(
    df: pd.DataFrame, class_names: dict, output_dir: str = "confusion_matrices"
) -> None:
    """
    Calculates and saves a normalized confusion matrix for each entry in a DataFrame.
    The confusion matrices are labeled with class names and saved as PNG files named after
    the model and combination identifiers.

    Args:
        df (pd.DataFrame): DataFrame containing the columns 'Model', 'Combination', 'y_true_label', and 'y_pred'.
        class_names (dict): Dictionary mapping class labels (int) to class names (str).
        output_dir (str): Directory where the confusion matrix plots will be saved. Defaults to 'confusion_matrices'.
    """

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Function to calculate and save a confusion matrix for a single DataFrame row
    def save_conf_matrix(row):
        # Calculate the confusion matrix and normalize it
        cm = confusion_matrix(row["y_true_label"], row["y_pred"])
        cm_normalized = cm.astype("float") / cm.sum(axis=1)[:, np.newaxis]

        # Create the plot
        plt.figure(figsize=(10, 8))
        sns.heatmap(
            cm_normalized,
            annot=True,
            fmt=".2f",
            cmap="Blues",
            xticklabels=[class_names[label][0] for label in sorted(class_names)],
            yticklabels=[class_names[label][0] for label in sorted(class_names)],
        )
        plt.title(f'Normalized Confusion Matrix: {row["Model"]}, {row["Combination"]}')
        plt.xlabel("Predicted Label")
        plt.ylabel("True Label")

        # Generate filename and save the plot
        filename = f"{output_dir}/{row['Model']}_{row['Combination']}.png".replace(
            " ", ""
        )
        plt.savefig(filename)
        plt.close()  # Close the plot to free memory
        print(f"Saved plot to {filename}")

    # Apply save_conf_matrix to each row in the DataFrame
    df.apply(save_conf_matrix, axis=1)


def plot_pred_vs_true(df, folder_name, class_names):
    """
    Creates and saves a plot for each row in the DataFrame, where each subplot within a plot
    corresponds to a unique class. Each class is plotted with its designated color and label.

    Parameters:
    - df (pandas.DataFrame): DataFrame containing the data for plots. Expected to have columns:
      'y_pred', 'y_true', 'y_true_label', 'Model', and 'Combination'.
    - folder_name (str): Directory name where the plots will be saved.
    - class_names (dict): Dictionary mapping class labels (int) to tuples of (class name, color).

    Each plot is saved with the filename format "Model_Combination.png", where spaces are removed.
    """

    # Ensure the directory exists where plots will be saved
    os.makedirs(folder_name, exist_ok=True)

    # Iterate over each row in the DataFrame to create plots
    for index, row in df.iterrows():
        y_pred = np.array(row["y_pred"])
        y_true = np.array(row["y_true"])
        y_true_label = np.array(row["y_true_label"])

        # Determine global axis limits
        x_min, x_max = y_true.min(), y_true.max()
        y_min, y_max = y_pred.min(), y_pred.max()

        x_min = min(0, x_min)
        y_min = min(0, y_min)

        # Setup for subplots
        plt.figure(figsize=(15, 30))
        unique_labels = np.unique(y_true_label)
        n_classes = len(unique_labels)
        red_line = np.linspace(-1, 1, 100)
        for i, label in enumerate(unique_labels, 1):
            ax = plt.subplot(n_classes, 1, i)

            # Plot all classes in gray as the background
            ax.scatter(y_true, y_pred, color="gray", alpha=0.2, label="Other Classes")

            # Highlight the current class
            idx = y_true_label == label
            class_color = class_names[label][1]  # Color corresponding to the label
            ax.scatter(
                y_true[idx],
                y_pred[idx],
                color=class_color,
                label=f"{class_names[label][0]}",
            )
            ax.plot(
                red_line, red_line, linewidth=3, alpha=0.4, linestyle="--", color="red"
            )

            # Set tick parameters
            ax.xaxis.set_major_locator(
                ticker.MultipleLocator(0.05)
            )  # Adjust tick spacing as needed
            ax.yaxis.set_major_locator(
                ticker.MultipleLocator(0.05)
            )  # Adjust tick spacing as needed
            ax.tick_params(direction="in", length=6, width=2)

            ax.set_title(f"{class_names[label][0]}")
            ax.set_xlabel("True Redshift")
            ax.set_ylabel("Predicted Redshift")
            ax.set_xlim(x_min, x_max)
            ax.set_ylim(y_min, y_max)
            ax.legend()
            ax.grid(True)

        # Format and save the file
        filename = f"{folder_name}/{row['Model']}_{row['Combination']}.png".replace(
            " ", ""
        )
        plt.savefig(filename)
        print(f"Saved plot to {filename}")
        plt.close()  # Close the plot to free up memory


def get_class_dependent_predictions(
    inputs: List[Dict[str, Any]], class_names: Dict[int, Tuple[str, str]]
) -> List[Dict[str, Any]]:
    """
    Segregates predictions and true values by class and calculates metrics for each class within
    each provided model and combination from the input data.

    Args:
        inputs (List[Dict[str, Any]]): A list of dictionaries, where each dictionary contains model output data including
                                       'y_pred', 'y_true', 'y_true_label', 'Model', 'Combination', and 'id'.
        class_names (Dict[int, Tuple[str, str]]): A dictionary mapping class labels (int) to tuples containing
                                            the class name (str) and its associated color (str).

    Returns:
        List[Dict[str, Any]]: A list of dictionaries where each dictionary contains calculated metrics for a class,
                              including the class name under the key 'class', and each key from the calculated metrics.
    """
    df = pd.DataFrame(inputs)
    results = []
    for index, row in df.iterrows():
        y_pred = torch.tensor(row["y_pred"])
        y_true = torch.tensor(row["y_true"])
        y_true_labels = torch.tensor(row["y_true_label"])

        # Process each class
        for label, name_color_tuple in class_names.items():
            class_name = name_color_tuple[0]  # Class name
            mask = y_true_labels == label

            # Segregate y_true and y_pred based on class
            y_pred_class = y_pred[mask]
            y_true_class = y_true[mask]
            if len(y_pred_class) > 0 and len(y_true_class) > 0:
                # Calculate metrics
                metrics, _ = calculate_metrics(
                    y_true=y_true_class,
                    y_pred=y_pred_class,
                    y_true_label=y_true_labels[mask],  # if needed by calculate_metrics
                    lc_data=None,
                    label=row["Model"],
                    combination=row["Combination"],
                    id=row["id"],
                    task="regression",  # or "redshift" based on your task
                )
                metrics["class"] = class_name
                # Collect results
                results.append(metrics)

    return results


def make_spider(
    df: pd.DataFrame,
    title: str,
    metric: str,
    output_dir: str,
    Range: Optional[Tuple[float, float]] = None,
) -> None:
    """
    Creates a radar plot for the specific metric across different classes, allowing the scale to be
    adjusted, and saves it to a file.

    Args:
        df (pd.DataFrame): DataFrame containing the metrics and class labels.
        title (str): Title of the plot, typically includes model, combination, and metric.
        metric (str): The specific metric to plot.
        output_dir (str): Directory where the plots will be saved.
        Range (Optional[Tuple[float, float]]): A tuple specifying the lower and upper limits for the plot's radial axis.
            If None, the plot scales automatically based on the data.

    Creates:
        A radar plot saved as a PNG file in the specified directory.
    """
    categories = df["class"].tolist()  # Classes as categories
    num_vars = len(categories)

    # Compute angle each bar
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]  # Complete the circle by appending the first angle at the end

    # The plot is made in a circular (not polygon) interface
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    # Extract the metric values and repeat the first value at the end to close the circle
    values = df[metric].tolist()
    values += values[:1]
    ax.fill(angles, values, color="blue", alpha=0.25)
    ax.plot(angles, values, color="blue", linewidth=2)

    # Set the range for the plot's radial axis if provided
    if Range is not None:
        ax.set_ylim(Range[0], Range[1])

    # Labels for each point
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=13)

    # Title of the plot
    plt.title(f"{title} - {metric}", size=15, color="blue", y=1.1)

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{title}_{metric}.png").replace(" ", "_")
    plt.savefig(output_path)
    print(f"Created radar plot in {output_path}")
    plt.close(fig)  # Close the plot after saving to free up memory


def generate_radar_plots(
    df: pd.DataFrame,
    output_dir: str,
    range_dict: Dict[str, Optional[Tuple[float, float]]],
) -> None:
    """
    Generates radar plots for each metric across different classes within each model and combination grouping
    from the input data and saves them to specified directory.

    Args:
        df (pd.DataFrame): DataFrame containing the metrics, class labels, and model/combination identifiers.
        output_dir (str): Directory where the radar plots will be saved.
        range_dict (Dict[str, Optional[Tuple[float, float]]]): Dictionary mapping metric names to tuples that specify
            the range (min, max) of the radar plot's radial axis. If the value is None, the plot scales automatically.

    Generates:
        Radar plots saved as PNG files in the specified output directory. Each plot is named according to its model,
        combination, and metric.
    """
    # Group by Model and Combination
    grouped = df.groupby(["Model", "Combination"])

    # Iterate through each group and metric to create radar plots
    for (model, combination), group in grouped:
        for metric in ["L1", "L2", "R2", "OLF"]:  # Define the metrics to iterate over
            title = f"{model} - {combination}"
            range_values = range_dict.get(
                metric, None
            )  # Get range for the metric, default to None if not specified
            make_spider(group, title, metric, output_dir, range_values)


def filter_classes(
    X_list: List[torch.Tensor],
    y: torch.Tensor,
    lc_data: Dict[str, torch.Tensor],
    target_classes: torch.Tensor,
) -> (List[torch.Tensor], torch.Tensor):
    """
    Filter a list of datasets based on target classes and automatically remap the class labels
    to start from 0 and increase sequentially.

    Parameters:
    - X_list (list of torch.Tensor): List of feature matrices.
    - y (torch.Tensor): The label vector.
    - lc_data (Dict[str, Tensor]): containing lc_data
    - target_classes (torch.Tensor): A tensor of the original class labels to keep.

    Returns:
    - list of torch.Tensor: List of filtered feature matrices.
    - torch.Tensor: Remapped label vector, consistent across all feature matrices.
    """
    # Flatten y to ensure it is a 1D tensor
    y_flat = y.flatten()

    # Create a mask for the elements of y that are in the target classes
    mask = y_flat == target_classes[:, None]
    mask = mask.any(dim=0)

    # Filter each X in the list based on the mask
    filtered_X_list = [X[mask] for X in X_list]
    if lc_data is not None:
        filtered_lc_data = {key: value[mask] for key, value in lc_data.items()}
    else:
        filtered_lc_data = None
    filtered_y = y_flat[mask]

    # Automatically generate new_labels based on the order in target_classes
    remapped_y = torch.empty_like(filtered_y)
    for i, class_val in enumerate(target_classes):
        remapped_y[filtered_y == class_val] = i

    return filtered_X_list, remapped_y, filtered_lc_data


def assert_sorted_lc(loader: Any, bands: List[Any]) -> None:
    """
    Check if the time sequences in each batch of the loader are sorted within each band.

    Parameters:
    loader (Any): A data loader that provides batches of data. Each batch is expected to be a tuple containing at least the following elements:
                  - mag_test: A list or array of magnitudes.
                  - time_test: A list or array of time sequences.
                  - padding_mask: A mask indicating padded elements.
                  - spec: Spectrum data.
                  - freq: Frequency data.
                  - maskspec: Masked spectrum data.
                  - redshift: Redshift data.
    bands (List[Any]): A list representing the bands for which the time sequences need to be checked.

    Raises:
    AssertionError: If any time sequence within a band is found to be unsorted.
    """
    nbands = len(bands)
    for batch in loader:
        _, mag_test, time_test, padding_mask, spec, freq, maskspec, redshift, _ = batch
        check = True
        for i in range(len(mag_test)):
            N = len(time_test[i])
            for k in range(nbands):
                test = (
                    time_test[i][(N // nbands) * k : (N // nbands) * (k + 1)]
                ).numpy()
                test = test[test != 0]
                check = check and (sorted(test) == test).all()
        assert check
