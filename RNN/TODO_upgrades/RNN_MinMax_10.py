import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
from pathlib import Path



# Load and preprocess the dataset --------------------------------------------
file_path = (Path(__file__).resolve().parent.parent.parent / '.data' / 'dataset' / 'XAU_1h_data_2004_to_2024-09-20.csv').as_posix()
data = pd.read_csv(file_path)

features = ['Open', 'High', 'Low', 'Close', 'Volume', 'MA_200', 'EMA_12-26', 'EMA_50-200', '%K', '%D', 'RSI']
target = 'future_close'

train_size = int(0.7 * len(data))
train_data = data.iloc[:train_size]
val_data = data.iloc[train_size:int(0.85 * len(data))]
test_data = data.iloc[int(0.85 * len(data)):]



# Normalize the data using Min-Max scaling ------------------------------------
train_min = {}
train_max = {}

for feature in features:
    train_min[feature] = train_data[feature].min()
    train_max[feature] = train_data[feature].max()

for feature in features:
    train_data[feature] = 2 * (train_data[feature] - train_min[feature]) / (train_max[feature] - train_min[feature]) - 1
    val_data[feature] = 2 * (val_data[feature] - train_min[feature]) / (train_max[feature] - train_min[feature]) - 1
    test_data[feature] = 2 * (test_data[feature] - train_min[feature]) / (train_max[feature] - train_min[feature]) - 1

target_min = train_data[target].min()
target_max = train_data[target].max()

train_data[target] = 2 * (train_data[target] - target_min) / (target_max - target_min) - 1
val_data[target] = 2 * (val_data[target] - target_min) / (target_max - target_min) - 1
test_data[target] = 2 * (test_data[target] - target_min) / (target_max - target_min) - 1



# Convert data to PyTorch tensors --------------------------------------------
def create_tensor_dataset(df, features, target):
    X = torch.tensor(df[features].values, dtype=torch.float32).unsqueeze(1)
    y = torch.tensor(df[target].values, dtype=torch.float32).unsqueeze(1)
    return X, y

train_X, train_y = create_tensor_dataset(train_data, features, target)
val_X, val_y = create_tensor_dataset(val_data, features, target)
test_X, test_y = create_tensor_dataset(test_data, features, target)



# Define the LSTM model -------------------------------------------------------
class LSTM(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, output_size):
        super(LSTM, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers=2, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        # Initialize hidden state and cell state
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        
        # Forward propagate LSTM
        out, _ = self.lstm(x, (h0, c0))
        
        # Decode the last time step
        out = self.fc(out[:, -1, :])
        return out



# Set hyperparameters and instantiate the model ------------------------------
input_size = train_X.shape[2] # Number of features (only training data, not target variable)
hidden_size = 128
num_layers = 1
num_epochs = 50
output_size = 1
lr = 0.001

# Instantiate the model, define loss function and optimizer
model = LSTM(input_size, hidden_size, num_layers, output_size)

class MAPELoss(nn.Module):
    def forward(self, y_pred, y_true):
        epsilon = 1e-8  # per evitare divisioni per zero
        return torch.mean(torch.abs((y_true - y_pred) / (y_true + epsilon))) * 100

criterion = nn.MSELoss()        # Mean Squared Error: sensibile agli outliers, per non sbagliare mai troppo
# criterion = nn.SmoothL1Loss() # Huber Loss: robusto agli outliers, ma meno sensibile ai picchi rispetto all'MSE
# criterion = MAPELoss()        # Mean Absolute Percentage Error: per valutare le previsioni in termini percentuali

optimizer = optim.RMSprop(model.parameters(), lr)
# optimizer = optim.Adam(model.parameters(), lr)



# Define the training function ------------------------------------------------
def train_model(model, train_X, train_y, val_X, val_y, criterion, optimizer, num_epochs):
    train_losses = []
    val_losses = []
    
    for epoch in range(num_epochs):
        model.train()
        optimizer.zero_grad()
        output = model(train_X)
        loss = criterion(output, train_y)
        loss.backward()
        optimizer.step()
        train_losses.append(loss.item())

        model.eval()
        with torch.no_grad():
            val_output = model(val_X)
            val_loss = criterion(val_output, val_y)
            val_losses.append(val_loss.item())

        if (epoch + 1) % 10 == 0:
            print(f'Epoch {epoch + 1}/{num_epochs}, Train Loss: {loss.item():.4f}, Val Loss: {val_loss.item():.4f}')
    
    return train_losses, val_losses



# Train the model -------------------------------------------------------------
train_losses, val_losses = train_model(model, train_X, train_y, val_X, val_y, criterion, optimizer, num_epochs)

# Plot the training and validation loss
plt.figure(figsize=(8, 5))
plt.plot(range(1, len(train_losses) + 1), train_losses, label="Training Loss", marker="o")
plt.plot(range(1, len(val_losses) + 1), val_losses, label="Validation Loss", marker="s")
plt.xlabel("Epoch")
plt.ylabel("Loss")
plt.title("Training vs Validation Loss")
plt.legend()
plt.grid(True)
plt.show()



# Evaluate the model on the test set ------------------------------------------
def evaluate_model(model, test_X, test_y, criterion):
    model.eval()
    test_loss = 0.0
    with torch.no_grad():
        for i in range(len(test_X)):
            x_test = test_X[i].unsqueeze(0)
            y_test = test_y[i].unsqueeze(0)
            output = model(x_test)
            loss = criterion(output, y_test)
            test_loss += loss.item()
    
    test_loss /= len(test_X)
    return test_loss

test_loss = evaluate_model(model, test_X, test_y, criterion)
print(f"Final Test Loss (LSMT_MinMax): {test_loss:.4f}")



# Inverse transform the predictions for graphical evaluation ------------------------------------------
def inverse_transform(preds, min_val, max_val):
    return (preds + 1) * (max_val - min_val) / 2 + min_val

model.eval()
predictions = []
actual_values = []

with torch.no_grad():
    for i in range(len(test_X)):
        x_test = test_X[i].unsqueeze(0)
        y_test = test_y[i].unsqueeze(0)
        pred = model(x_test)
        predictions.append(pred.item())
        actual_values.append(y_test.item())

predictions = inverse_transform(np.array(predictions), target_min, target_max)
actual_values = inverse_transform(np.array(actual_values), target_min, target_max)

plt.figure(figsize=(12, 6))
plt.plot(actual_values, label="Actual Price", color='blue', linewidth=2)
plt.plot(predictions, label="Predicted Price", color='red', linestyle='dashed', linewidth=2)
plt.xlabel("Time")
plt.ylabel("Price")
plt.title("Actual vs Predicted Price (Test Set)")
plt.legend()
plt.grid(True)
plt.show()