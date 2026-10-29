"""Decode original JPEG on the Jetson once. PNG decode is excluded from timing."""
import cv2
import numpy as np
from common import *

def main():
    assert not (ROOT/'input_manifest.json').exists(),'Input manifest already exists; retain old attempt'
    source=load(ROOT/'dataset/dataset_manifest.json');rows=source['frames']
    assert len(rows)==400
    (ROOT/'inputs').mkdir(exist_ok=False);frames=[];pixels=set()
    for r in rows:
        original=ROOT/r['path'];assert sha(original)==r['file_sha256']
        im=cv2.imread(str(original),cv2.IMREAD_COLOR);assert im is not None and im.shape[:2]==(r['height'],r['width'])
        h=hashlib.sha256(im.tobytes()).hexdigest();assert h not in pixels;pixels.add(h)
        dest=ROOT/'inputs'/(r['frame_id']+'.png');assert cv2.imwrite(str(dest),im)
        back=cv2.imread(str(dest));assert np.array_equal(im,back)
        frames.append(dict(frame_id=r['frame_id'],path=str(dest.relative_to(ROOT)),source=r['path'],source_sha256=r['file_sha256'],coco_image_id=r['coco_image_id'],group=r['group'],width=r['width'],height=r['height'],file_sha256=sha(dest),pixel_sha256=h))
    save(ROOT/'input_manifest.json',dict(dataset_id=source['dataset_id'],rule='Frozen reviewed COCO val2017 200 positives + 200 negatives; same shuffled order in all workers',frames=frames,jpeg_decode=cv2.__version__))
    cfg=load(ROOT/'config.json');cfg['manifest_sha256']=sha(ROOT/'input_manifest.json');save(ROOT/'config.json',cfg)
    print('Prepared 400 unique BGR inputs; positive=200, negative=200')

if __name__=='__main__':main()
