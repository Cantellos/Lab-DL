import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
from pathlib import Path

# TODO: finding loss + optimizer combo with best performance

# Set the device for execution on GPU if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

pd.options.mode.copy_on_write = True


# ===== 1. Loading and Normalizing the Dataset =====
# Load the dataset
file_path = (Path(__file__).resolve().parent.parent / '.data' / 'dataset' / 'XAU_1d_data_2004_to_2024-09-20.csv').as_posix()
data = pd.read_csv(file_path)

# Choose features and target
features = ['Open', 'High', 'Low', 'Close', 'Volume', 'MA_200', 'EMA_12-26', 'EMA_50-200', '%K', '%D', 'RSI']
target = 'future_close'

# Split dataset (70% train, 15% val, 15% test)
train_size = int(len(data) * 0.7)   
val_size = int(len(data) * 0.15)

training = data[:train_size]
validation = data[train_size:train_size + val_size]
testing = data[train_size + val_size:]

# Normalize features feature by feature
scaler = MinMaxScaler()

# Fit only on the training set, but transform all of them using the same scaler
scaler.fit(training[features])

train_data = scaler.transform(training[features])
val_data = scaler.transform(validation[features])
test_data = scaler.transform(testing[features])

# Normalize target variable (future_close) separately
scaler.fit(training[[target]])

train_target = scaler.transform(training[[target]])
val_target = scaler.transform(validation[[target]])
test_target = scaler.transform(testing[[target]])

# Convert data to PyTorch tensors
def create_tensor_dataset(data, target):
    # Add dimension to ensure the correct shape for RNN input
    x = torch.tensor(data, dtype=torch.float32).unsqueeze(1)  # Add sequence dimension
    y = torch.tensor(target, dtype=torch.float32)
    return x, y

train_x, train_y = create_tensor_dataset(train_data, train_target)
val_x, val_y = create_tensor_dataset(val_data, val_target)
test_x, test_y = create_tensor_dataset(test_data, test_target)


# ===== 2. Definition of the MLP (Fully Connected Layer) =====
class FullyConnected(nn.Module):
    def __init__(self, input_size, hidden_size, output_size):
        super(FullyConnected, self).__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        out = self.fc1(x)
        out = self.relu(out)
        out = self.fc2(out)
        return out

input_size = len(features)
hidden_size = 64
output_size = 1
lr=0.001

model = FullyConnected(input_size, hidden_size, output_size)

# criterion = nn.SmoothL1Loss()
criterion = nn.MSELoss()

# optimizer = optim.Adam(model.parameters(), lr)
optimizer = optim.RMSprop(model.parameters(), lr)

# ===== 3. Training Function =====
def train_model(model, train_x, train_y, val_x, val_y, criterion, optimizer, num_epochs):
    train_losses = []
    val_losses = []
    patience = 5  # Number of epochs to wait for improvement
    best_val_loss = float('inf')
    epochs_no_improve = 0

    for epoch in range(num_epochs):

        # Training
        model.train()
        train_loss = 0.0
        optimizer.zero_grad()
        for i in range(len(train_x)):
            output = model(train_x)
            loss = criterion(output[i], train_y[i])
            loss.backward()
            train_loss += loss.item()
            optimizer.step()

        train_loss /= len(train_data)
        train_losses.append(train_loss.item())  

        # Validation
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for i in range(len(val_data)):
                val_output = model(val_x)
                loss = criterion(val_output, val_y)
                val_loss += loss.item()

            val_loss /= len(val_data)
            val_losses.append(val_loss.item())

        print(f'Epoch {epoch+1}/{num_epochs}, Train Loss: {train_losses[-1]:.6f}, Val Loss: {val_losses[-1]:.6f}')

        # Early stopping condition
        if val_losses[-1] < best_val_loss:
            best_val_loss = val_losses[-1]
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1

        if epochs_no_improve >= patience:
            print(f"Early stopping at epoch {epoch+1} due to no improvement in validation loss for {patience} epochs.")
            break

    return train_losses, val_losses


# ===== 4. Training the Model =====
num_epochs = 20
train_losses, val_losses = train_model(model, train_x, train_y, val_x, val_y, criterion, optimizer, num_epochs)


# ===== 5. Plotting the Losses =====
plt.figure(figsize=(11,6))
plt.plot(range(3, len(train_losses) + 1), train_losses[2:], label='Train Loss', marker='o')
plt.plot(range(3, len(val_losses) + 1), val_losses[2:], label='Validation Loss', marker='s')
plt.legend()
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.title('Training and Validation Loss (excluding first 2 for graphic reasons)')
plt.show()


# ===== 6. Testing the Model =====
model.eval()
test_loss = 0.0
predictions = []
actuals = []

with torch.no_grad():
    for i in range(len(test_data)):
        output = model(test_x)
        loss = criterion(output, test_y)
        test_loss += loss.item()
        
        predictions.extend(output)
        actuals.extend(test_y[i])

final_test_loss = test_loss / len(test_data)
print(f'\nMSE Loss - Test set (MLP): {final_test_loss:.6f}')


# Accuracy Loss 
def accuracy_based_loss(predictions, targets, threshold):
    accuracy = 0
    corrects = 0
    # Calculate the number of correct predictions within the threshold
    for length in range(len(predictions)):
        if abs(predictions[length] - targets[length]) <= threshold*targets[length]:
            corrects += 1
    # Calculate the loss as the ratio of incorrect predictions
    accuracy = corrects / len(predictions)
    return accuracy

loss = accuracy_based_loss(predictions, actuals, threshold=0.02)  # 2% tolerance
print(f'\nAccuracy - Test set (MLP): {loss*100:.4f}% of correct predictions within 2%\n')


# Plot Actual vs Predicted Prices
plt.figure(figsize=(12, 6))
plt.plot(actuals, label='Actual', color='blue')
plt.plot(predictions, label='Predicted', color='red')
plt.xlabel("Time")
plt.ylabel("Price")
plt.title("Actual vs Predicted Prices")
plt.legend()
plt.grid(True)
plt.show()