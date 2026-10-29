import json
from pathlib import Path
import tensorrt as trt

def inspect_engine(path):
 data=Path(path).read_bytes(); metadata={}
 try:
  length=int.from_bytes(data[:4],'little'); metadata=json.loads(data[4:4+length]); data=data[4+length:]
 except (ValueError,UnicodeError):pass
 logger=trt.Logger(trt.Logger.WARNING); runtime=trt.Runtime(logger); engine=runtime.deserialize_cuda_engine(data)
 if engine is None:raise RuntimeError('Cannot deserialize engine')
 io=[dict(name=engine.get_tensor_name(i),shape=list(engine.get_tensor_shape(engine.get_tensor_name(i))),dtype=str(engine.get_tensor_dtype(engine.get_tensor_name(i))),mode=str(engine.get_tensor_mode(engine.get_tensor_name(i)))) for i in range(engine.num_io_tensors)]
 inspector=engine.create_engine_inspector(); layers=inspector.get_engine_information(trt.LayerInformationFormat.JSON)
 return dict(metadata=metadata,io=io,layers=layers)
