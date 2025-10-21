import torch
import torch.nn as nn


class SimpleDetector(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(4, 16), nn.ReLU(), nn.Linear(16, 2))

    def forward(self, x):
        return self.fc(x)


def run_infer():
    model = SimpleDetector()
    try:
        model.load_state_dict(torch.load('ai/simple_detector.pt'))
    except Exception:
        print('No model found, returning dummy')
        return {"anomaly": False, "confidence": 0.1}

    model.eval()
    sample = torch.randn(1, 4)
    logits = model(sample)
    probs = torch.softmax(logits, dim=1)
    anom = int(probs[0, 1] > 0.5)
    return {"anomaly": bool(anom), "confidence": float(probs[0, 1].item())}


if __name__ == '__main__':
    print(run_infer())
