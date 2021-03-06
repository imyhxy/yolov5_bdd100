import torch
from torchvision.ops.boxes import nms
from commons.boxs_utils import box_iou,xywh2xyxy




def non_max_suppression(prediction,
                        conf_thresh=0.1,
                        iou_thresh=0.6,
                        merge=False,
                        agnostic=False,
                        multi_label=True,
                        max_det=300):
    """Performs Non-Maximum Suppression (NMS) on inference results

    Args:
    prediction(torch.Tensor): shape=[bs.-1,no(85)] note: box cords (x,y,w,h) have been decoded into input size.

    Returns:
         a list(len=bs) with element's shape: nx6 (x1, y1, x2, y2, conf, cls)
    """

    xc = prediction[..., 4] > conf_thresh  # candidates
    # Settings
    min_wh, max_wh = 2, 4096  # (pixels) minimum and maximum box width and height
    redundant = True  # require redundant detections
    output = [None] * prediction.shape[0]     # list len=bs

    for xi, x in enumerate(prediction):  # image index, image inference
        # Apply constraints
        # x[((x[..., 2:4] < min_wh) | (x[..., 2:4] > max_wh)).any(1), 4] = 0  # width-height
        x = x[xc[xi]]   # if confidence score/ objectness < conf_thres, passed it

        # If none remain process next image
        if not x.shape[0]:
            continue

        # Compute conf
        x[:, 5:] *= x[:, 4:5]  # conf = obj_conf * cls_conf

        # Box (center x, center y, width, height) to (x1, y1, x2, y2)
        box = xywh2xyxy(x[:, :4])

        # Detections matrix nx6 (xyxy, conf, cls)
        if multi_label:
            i, j = (x[:, 5:] > conf_thresh).nonzero(as_tuple=False).T    # (i,j) i索引1 j索引2
            # 一个Box选择置信度大于阈值的类别做预测,  note: x[i, j + 5, None]==> x[i,j+5]????
            x = torch.cat((box[i], x[i, j + 5, None], j[:, None].float()), 1)
        else:  # best class only
            # best class only( 一个Box只选择其中置信度最高的类别)
            conf, j = x[:, 5:].max(1, keepdim=True)
            x = torch.cat((box, conf, j.float()), 1)[conf.view(-1) > conf_thresh]    # 二次筛选，排除掉最终的class_score<conf_thresh的标签

        # Filter by class

        # Apply finite constraint
        # if not torch.isfinite(x).all():
        #     x = x[torch.isfinite(x).all(1)]

        # If none remain process next image
        n = x.shape[0]  # number of boxes
        if not n:
            continue

        # Sort by confidence
        # x = x[x[:, 4].argsort(descending=True)]

        # Batched NMS
        c = x[:, 5:6] * (0 if agnostic else max_wh)  # 按照类别加入偏置量
        '''
            按照类别拉大不同类别之间的box间距，为之后的maxtrix weight加权合并奠定基础（即加权合并主要在同类别的bbox之间进行）
        '''
        boxes, scores = x[:, :4] + c, x[:, 4]  # boxes (offset by class), scores
        i = nms(boxes, scores, iou_thresh)
        if i.shape[0] > max_det:  # limit detections
            i = i[:max_det]
        if merge and (1 < n < 3E3):  # Merge NMS (boxes merged using weighted mean)
            try:  # update boxes as boxes(i,4) = weights(i,n) * boxes(n,4)
                iou = box_iou(boxes[i], boxes) > iou_thresh  # iou matrix
                weights = iou * scores[None]  # box weights
                x[i, :4] = torch.mm(weights, x[:, :4]).float() / weights.sum(1, keepdim=True)  # merged boxes
                if redundant:
                    i = i[iou.sum(1) > 1]  # require redundancy
            except:  # possible CUDA error https://github.com/ultralytics/yolov3/issues/1139
                print(x, i, x.shape, i.shape)
                pass

        output[xi] = x[i]

    return output


