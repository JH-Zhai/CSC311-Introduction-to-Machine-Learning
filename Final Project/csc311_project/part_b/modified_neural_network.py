from utils import *
from torch.autograd import Variable

import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.utils.data

import numpy as np
import torch

import matplotlib.pyplot as plt


def load_data(base_path="../data"):
    """ Load the data in PyTorch Tensor.

    :return: (zero_train_matrix, train_data, valid_data, test_data)
        WHERE:
        zero_train_matrix: 2D sparse matrix where missing entries are
        filled with 0.
        train_data: 2D sparse matrix
        valid_data: A dictionary {user_id: list,
        user_id: list, is_correct: list}
        test_data: A dictionary {user_id: list,
        user_id: list, is_correct: list}
    """
    train_matrix = load_train_sparse(base_path).toarray()
    valid_data = load_valid_csv(base_path)
    test_data = load_public_test_csv(base_path)

    zero_train_matrix = train_matrix.copy()
    # Fill in the missing entries to 0.
    zero_train_matrix[np.isnan(train_matrix)] = 0
    # Change to Float Tensor for PyTorch.
    zero_train_matrix = torch.FloatTensor(zero_train_matrix)
    train_matrix = torch.FloatTensor(train_matrix)

    return zero_train_matrix, train_matrix, valid_data, test_data


class AutoEncoder(nn.Module):
    def __init__(self, num_question, k=100):
        """ Initialize a class AutoEncoder.

        :param num_question: int
        :param k: int
        """
        super(AutoEncoder, self).__init__()

        # Define linear functions.
        self.g = nn.Linear(num_question, k)
        self.hidden = nn.Linear(k, k)
        self.h = nn.Linear(k, num_question)

    def get_weight_norm(self):
        """ Return ||W^1||^2 + ||W^2||^2.

        :return: float
        """
        g_w_norm = torch.norm(self.g.weight, 2) ** 2
        hidden_w_norm = torch.norm(self.hidden.weight, 2) ** 2
        h_w_norm = torch.norm(self.h.weight, 2) ** 2
        return g_w_norm + h_w_norm

    def forward(self, inputs):
        """ Return a forward pass given inputs.

        :param inputs: user vector.
        :return: user vector.
        """
        out = inputs
        out = self.g(out)
        out = torch.sigmoid(out)
        out = self.hidden(out)
        out = torch.sigmoid(out)
        out = self.h(out)
        out = torch.sigmoid(out)
        return out


def train(model, lr, lamb, train_data, zero_train_data, valid_data, num_epoch):
    """ Train the neural network, where the objective also includes
    a regularizer.

    :param model: Module
    :param lr: float
    :param lamb: float
    :param train_data: 2D FloatTensor
    :param zero_train_data: 2D FloatTensor
    :param valid_data: Dict
    :param num_epoch: int
    :return: None
    """
    # Define optimizers and loss function.
    optimizer = optim.SGD(model.parameters(), lr=lr)
    optimizer_final = optim.SGD(model.parameters(), lr=lr*0.5)
    num_student = train_data.shape[0]
    train_loss_lst = []
    valid_acc_lst = []

    val_loss_min = np.inf
    epochs_no_improve = 0
    max_epochs_no_improve = 5

    for epoch in range(0, num_epoch):
        train_loss = 0.

        if epoch >= 40:
            optimizer = optimizer_final

        model.train()
        for user_id in range(num_student):
            inputs = Variable(zero_train_data[user_id]).unsqueeze(0)
            target = inputs.clone()

            optimizer.zero_grad()
            output = model(inputs)

            # Mask the target to only compute the gradient of valid entries.
            nan_mask = np.isnan(train_data[user_id].unsqueeze(0).numpy())
            target[0][nan_mask] = output[0][nan_mask]

            loss = torch.sum((output - target) ** 2.) + lamb / 2 * model.get_weight_norm()
            loss.backward()

            train_loss += loss.item()
            optimizer.step()

        # early stopping
        # with torch.no_grad():
        #     model.eval()
        #
        #     val_loss = lamb / 2 * model.get_weight_norm()
        #     for i, user_id in enumerate(valid_data['user_id']):
        #         label = valid_data['is_correct'][i]
        #         predict = output[0][valid_data['question_id'][i]].item()
        #         val_loss += (predict - label) ** 2.
        #     print('validation loss {}'.format(val_loss))
        #
        #     if val_loss < val_loss_min:
        #         val_loss_min = val_loss
        #         epochs_no_improve = 0
        #     else:
        #         epochs_no_improve += 1
        #         if epochs_no_improve > max_epochs_no_improve:
        #             print('Early stopping')
        #             break


        valid_acc = evaluate(model, zero_train_data, valid_data)
        train_loss_lst.append(train_loss)
        valid_acc_lst.append(valid_acc)
        print("Epoch: {} \tTraining Cost: {:.6f}\t "
              "Valid Acc: {}".format(epoch, train_loss, valid_acc))

    # report final validation accuracy
    print('Final validation accuracy: {}'.format(valid_acc_lst[-1]))

    fig = plt.figure(figsize=(10, 5))
    ax1 = fig.add_subplot(121)
    ax2 = fig.add_subplot(122)

    ax1.plot([i for i in range(len(valid_acc_lst))], valid_acc_lst, label='val accuracy')
    ax1.set_xlabel('Number of epochs')
    ax2.plot([i for i in range(len(train_loss_lst))], train_loss_lst, label='training loss')
    ax2.set_xlabel('Number of epochs')
    plt.show()


def evaluate(model, train_data, valid_data):
    """ Evaluate the valid_data on the current model.

    :param model: Module
    :param train_data: 2D FloatTensor
    :param valid_data: A dictionary {user_id: list,
    question_id: list, is_correct: list}
    :return: float
    """
    # Tell PyTorch you are evaluating the model.
    model.eval()

    total = 0
    correct = 0

    for i, u in enumerate(valid_data["user_id"]):
        inputs = Variable(train_data[u]).unsqueeze(0)
        output = model(inputs)

        guess = output[0][valid_data["question_id"][i]].item() >= 0.5
        if guess == valid_data["is_correct"][i]:
            correct += 1
        total += 1
    return correct / float(total)


def main():
    zero_train_matrix, train_matrix, valid_data, test_data = load_data()

    # Set model hyperparameters.
    k = 50
    model = AutoEncoder(train_matrix.shape[1], k)

    # Set optimization hyperparameters.
    lr = 0.015
    num_epoch = 80
    lamb = 0.
    train(model, lr, lamb, train_matrix, zero_train_matrix,
          valid_data, num_epoch)

    # final test accuracy
    test_acc = evaluate(model, zero_train_matrix, test_data)
    print('Final test accuracy: {}'.format(test_acc))


if __name__ == "__main__":
    main()