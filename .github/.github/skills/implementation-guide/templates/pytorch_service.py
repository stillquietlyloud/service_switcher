from typing import Any, Dict
import torch


class TorchInferenceService:
    def __init__(self, model_path: str) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model(model_path)

    def _load_model(self, model_path: str) -> torch.nn.Module:
        model = torch.jit.load(model_path, map_location=self.device)
        model.eval()
        return model

    def predict(self, features: torch.Tensor) -> Dict[str, Any]:
        with torch.no_grad():
            inputs = features.to(self.device)
            outputs = self.model(inputs)
        return {"predictions": outputs.cpu().tolist()}
