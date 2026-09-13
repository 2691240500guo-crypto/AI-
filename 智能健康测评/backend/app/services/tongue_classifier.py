"""Small multi-task classifier used by the F9 tongue observation flow."""

import torch
from torch import nn


class TongueMultiHeadClassifier(nn.Module):
    """Shared image encoder with 3-class tongue-colour and coating heads."""

    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 24, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(24, 48, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(48, 96, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.dropout = nn.Dropout(0.15)
        self.color_head = nn.Linear(96, 3)
        self.coat_head = nn.Linear(96, 3)

    def forward(self, x):
        features = self.dropout(self.encoder(x).flatten(1))
        return self.color_head(features), self.coat_head(features)
