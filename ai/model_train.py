"""Minimal AI training script using PyTorch - trains a tiny model on dummy data."""
import torch
import torch.nn as nn
import torch.optim as optim


class SimpleDetector(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(4, 16), nn.ReLU(), nn.Linear(16, 2))

    def forward(self, x):
        return self.fc(x)


def generate_dummy_data(n=100):
    X = torch.randn(n, 4)
    y = (X.sum(dim=1) > 0).long()
    return X, y


def train():
    X, y = generate_dummy_data(200)
    model = SimpleDetector()
    loss_fn = nn.CrossEntropyLoss()
    opt = optim.Adam(model.parameters(), lr=1e-3)

    for epoch in range(3):
        logits = model(X)
        loss = loss_fn(logits, y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        print(f"epoch={epoch} loss={loss.item():.4f}")

    torch.save(model.state_dict(), 'ai/simple_detector.pt')
    print('model saved to ai/simple_detector.pt')


if __name__ == '__main__':
    train()
