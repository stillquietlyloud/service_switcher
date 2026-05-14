from typing import Any, Dict
import tensorflow as tf


class TensorFlowInferenceService:
    def __init__(self, model_path: str) -> None:
        self.model = tf.saved_model.load(model_path)

    def predict(self, tensor: tf.Tensor) -> Dict[str, Any]:
        output = self.model(tensor)
        if hasattr(output, "numpy"):
            return {"predictions": output.numpy().tolist()}
        return {"predictions": str(output)}
