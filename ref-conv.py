# Inputs: HxWxCxN, Filters: RxSxCxM, Output: ExFxMxN, P = padding, T = stride
# E = (H + 2P - R)/T + 1
# F = (W + 2P - S)/T + 1
# params = (RSC + 1)M
import argparse
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from time import time
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.optim.lr_scheduler import StepLR
from torchvision import datasets, transforms

mpl.use('Agg')


class Flatten(nn.Module):
    def forward(self, input):
        # Flatten the 4-dimensional array into 2 dimensions
        return input.view(input.size(0), -1)


"""
CNN model:
Input: 28x28, 1 channel
Conv1: 32 3x3 filters, stride 1 -> 32x26x26 output, ReLU activation
Conv2: 64 3x3 filters, stride 1 -> 64x24x24 output, ReLU activation
MaxPool: downscale by 2 -> 64x12x12 output
Flatten: 64*12*12 = 9216 layers
FC1: 9216 -> 128 layers, ReLU activation
FC2: 128 -> 10 layers
"""
Model = torch.nn.Sequential(
    nn.Conv2d(1, 32, kernel_size=3),
    nn.ReLU(),
    nn.Conv2d(32, 64, kernel_size=3),
    nn.ReLU(),
    nn.MaxPool2d(kernel_size=2),  # stride = kernel_size
    Flatten(),
    nn.Linear(9216, 128),
    nn.ReLU(),
    nn.Linear(128, 10)
)


def train(model, device, train_loader, optimizer, loss, epoch):
    # Set the model to training mode
    model.train()
    # Store all the loss values for the graph
    tmp_loss = []

    for batch_idx, (data, target) in enumerate(train_loader):
        # Forward pass
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)

        if loss == 'CE':
            # CrossEntropy Loss
            loss_fn = nn.CrossEntropyLoss()
        else:
            # MSE Loss
            # Prepare for one-hot labels
            y_one_hot = target.numpy()
            y_one_hot = (np.arange(10) == y_one_hot[:, None]).astype(np.float32)
            target = torch.from_numpy(y_one_hot)
            loss_fn = nn.MSELoss()

        # Compute the loss and perform backward propagation
        loss_ = loss_fn(output, target)
        loss_.backward()
        optimizer.step()

        # Print the progress every log interval
        if batch_idx % FLAGS.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss_.item()))
            tmp_loss.append(loss_.item())

    return tmp_loss


def test(model, device, test_loader):
    # Set the model to testing mode
    model.eval()
    test_loss = 0
    correct = 0

    with torch.no_grad():
        for data, target in test_loader:
            # Compute the loss after a forward pass
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction='sum').item()  # sum up batch loss

            pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset)))


def main():
    # Use either the CPU or GPU
    no_cuda = False
    use_cuda = not no_cuda and torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")

    # Load the MNIST dataset
    # x_train: 60Kx28x28, y_train: 60K, x_test: 10Kx28x28, y_test: 10K
    batch_size = FLAGS.train_batch_size
    test_batch_size = FLAGS.test_batch_size

    train_loader = torch.utils.data.DataLoader(
        datasets.MNIST(FLAGS.data_dir, train=True, download=True,
                       transform=transforms.Compose([
                           transforms.ToTensor(),
                           transforms.Normalize((0.1307,), (0.3081,))
                       ])),
        batch_size=batch_size, shuffle=True)

    test_loader = torch.utils.data.DataLoader(
        datasets.MNIST(FLAGS.data_dir, train=False, transform=transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.1307,), (0.3081,))
        ])),
        batch_size=test_batch_size, shuffle=True)

    # Set the optimizer to update the weights and bias
    lr = FLAGS.lr
    model = Model.to(device)
    optimizer = optim.SGD(model.parameters(), lr=lr)
    # Training settings
    epochs = FLAGS.epochs
    loss = FLAGS.loss_fn

    if FLAGS.start_checkpoint:
        ckpt = torch.load(FLAGS.start_checkpoint)
        model.load_state_dict(ckpt)

    # Start training
    time0 = time()
    loss_values = []
    # Decay the learning rate 70% every epoch
    scheduler = StepLR(optimizer, step_size=1, gamma=0.7)

    for epoch in range(1, epochs + 1):
        _ = train(model, device, train_loader, optimizer, loss, epoch)
        loss_values.extend(_)
        test(model, device, test_loader)
        scheduler.step()

    if FLAGS.save_model:
        torch.save(model.state_dict(), FLAGS.save_checkpoint)

    time1 = time()
    # Plot the training loss
    plt.figure()
    plt.title("Training Loss Over Epochs")
    plt.xlabel("Epoch")
    plt.ylabel("Training Loss")
    # Align the x values to the correct epoch number
    epoch_values = np.arange(1, len(loss_values) + 1, dtype=np.float)
    epoch_values *= FLAGS.train_batch_size * FLAGS.log_interval
    epoch_values /= len(train_loader.dataset)
    plt.xticks(np.arange(1, 11))
    plt.plot(epoch_values, loss_values)
    plt.savefig(FLAGS.loss_fig)
    print('Training and Testing total execution time is: %s seconds ' % (time1 - time0))


if __name__ == '__main__':
    # Read all the command line arguments, or supply default values
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', type=str, default='downloads',
                        help='Where to download the MNIST data to')
    parser.add_argument('--train_batch_size', type=int, default=128, metavar='N',
                        help='input batch size for training')
    parser.add_argument('--test_batch_size', type=int, default=10000, metavar='N',
                        help='input batch size for testing')
    parser.add_argument('--loss_fn', type=str, default='CE',
                        help='select one loss function from CE and MSE')
    parser.add_argument('--epochs', type=int, default=10, metavar='N',
                        help='number of epochs to train')
    parser.add_argument('--lr', type=float, default=0.10, metavar='LR',
                        help='learning rate ')
    parser.add_argument('--log_interval', type=int, default=100, metavar='N',
                        help='how many batches to wait before logging training status')
    parser.add_argument('--start_checkpoint', type=str, default=None,  # or "mnist_cnn.pth",
                        help='If specified, restore this pretrained model before any training.')
    parser.add_argument('--save_model', action='store_true', default=False,
                        help='For Saving the current Model')
    parser.add_argument('--save_checkpoint', type=str, default="downloads/mnist_cnn.pth",
                        help='Save the trained model.')
    parser.add_argument('--loss_fig', type=str, default='downloads/loss_curve.png',
                        help='Where to save the plotted training loss curve.')
    FLAGS, _ = parser.parse_known_args()
    main()
