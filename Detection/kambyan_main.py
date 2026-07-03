import os 
import cv2
import time
import numpy as np
try:
    import tensorflow as tf
except ImportError:
    tf = None
import six
import csv
import math
import pandas as pd
from pandas import DataFrame
import datetime
from pathlib import Path
import shutil

# importing the multiprocessing module
import multiprocessing
from Detection.kambyanModel import label_map_util


DETECTION_CONFIDENCE_THRESHOLD = 0.6
DUPLICATE_POINT_DISTANCE = int(os.environ.get("KAMBYAN_DUPLICATE_POINT_DISTANCE", "30"))
DUPLICATE_DISTANCE_REFERENCE_DIMENSION = int(os.environ.get("KAMBYAN_DUPLICATE_DISTANCE_REFERENCE_DIMENSION", "7707"))
TILE_SIZE = (480, 480)
TILE_OFFSET = (430, 430)
DETECTION_COLUMNS = [
    "ids",
    "score",
    "x_coordinate",
    "y_coordinate",
    "xmin",
    "ymin",
    "xmax",
    "ymax",
    "row",
    "column",
    "heigth",
    "width",
]


def safe_rmtree(path, attempts=6, delay=0.5):
    for attempt in range(attempts):
        try:
            if os.path.exists(path):
                shutil.rmtree(path)
            return True
        except PermissionError as error:
            if attempt == attempts - 1:
                print("Warning: unable to remove locked detection folder {}: {}".format(path, error))
                return False
            time.sleep(delay)
    return False


def get_rows(centers, row_amt, row_h):
    centers = np.array(centers)
    if len(centers) == 0 or row_amt <= 0:
        return
    d = row_h / row_amt
    for i in range(row_amt):
        f = centers[:, 1] - d * i
        a = centers[(f < d) & (f > 0)]
        yield a[a.argsort(0)[:, 0]]


def duplicate_point_distance_for_image(image_shape):
    if DUPLICATE_DISTANCE_REFERENCE_DIMENSION <= 0:
        return DUPLICATE_POINT_DISTANCE

    image_height = int(image_shape[0])
    image_width = int(image_shape[1])
    scale = max(image_width, image_height) / float(DUPLICATE_DISTANCE_REFERENCE_DIMENSION)
    return max(DUPLICATE_POINT_DISTANCE, int(round(DUPLICATE_POINT_DISTANCE * scale)))


def merge_duplicate_detections(rows, duplicate_distance):
    clusters = []
    for row in rows:
        x_coordinate = float(row["x_coordinate"])
        y_coordinate = float(row["y_coordinate"])
        best_cluster = None
        best_distance = None

        for cluster in clusters:
            distance = math.hypot(x_coordinate - cluster["x"], y_coordinate - cluster["y"])
            if distance < duplicate_distance and (best_distance is None or distance < best_distance):
                best_cluster = cluster
                best_distance = distance

        score = max(float(row.get("score") or 0), 0.001)
        if best_cluster is None:
            clusters.append({
                "rows": [row],
                "x_sum": x_coordinate * score,
                "y_sum": y_coordinate * score,
                "weight_sum": score,
                "x": x_coordinate,
                "y": y_coordinate,
            })
            continue

        best_cluster["rows"].append(row)
        best_cluster["x_sum"] += x_coordinate * score
        best_cluster["y_sum"] += y_coordinate * score
        best_cluster["weight_sum"] += score
        best_cluster["x"] = best_cluster["x_sum"] / best_cluster["weight_sum"]
        best_cluster["y"] = best_cluster["y_sum"] / best_cluster["weight_sum"]

    merged_rows = []
    merged_cluster_count = 0
    for cluster in clusters:
        if len(cluster["rows"]) > 1:
            merged_cluster_count += 1
        merged_row = max(cluster["rows"], key=lambda item: float(item.get("score") or 0)).copy()
        merged_row["x_coordinate"] = round(cluster["x"], 2)
        merged_row["y_coordinate"] = round(cluster["y"], 2)
        merged_rows.append(merged_row)

    return merged_rows, merged_cluster_count


def image_tiling(image_file, images_folder):
    print ('Image_Tiling: Starting')
    img = cv2.imread(str(image_file)) 
    if img is None:
        raise FileNotFoundError("Unable to read image file: {}".format(image_file))
    name = Path(image_file).stem

    img_shape = img.shape
    tile_size = (480, 480)
    offset = (430,430)

    for i in range(int(math.ceil(img_shape[0]/(offset[1] * 1.0)))):
        for j in range(int(math.ceil(img_shape[1]/(offset[0] * 1.0)))):
            y1 = offset[1]*i
            y2 = min(offset[1]*i+tile_size[1], img_shape[0])
            x1 = offset[0]*j
            x2 = min(offset[0]*j+tile_size[0], img_shape[1])
            cropped_img = img[y1:y2, x1:x2]
            if (x2-x1) > 33 and (y2-y1) > 33:
                # Debugging the tiles
                cv2.imwrite(str(images_folder)+"/"+name+"_r" + str(i) + "_c" + str(j) + ".png", cropped_img)
    print ('Image_Tiling: End')
    return img_shape, offset


class PalmOilTreeDetector:
    def __init__(self):
        if tf is None:
            raise ImportError("TensorFlow is not installed. Install TensorFlow to run detection.")
        cwd_path = Path(__file__).resolve().parent.parent
        model_path = os.path.join(cwd_path, "Detection/kambyanModel")
        path_to_ckpt = os.path.join(model_path, 'frozen_inference_graph.pb')
        path_to_labels = os.path.join(model_path, 'labelmap.pbtxt')
        label_map = label_map_util.load_labelmap(path_to_labels)
        categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=1, use_display_name=True)
        self.category_index = label_map_util.create_category_index(categories)
        self.detection_graph = tf.Graph()
        with self.detection_graph.as_default():
            od_graph_def = tf.compat.v1.GraphDef()
            with tf.compat.v2.io.gfile.GFile(path_to_ckpt, 'rb') as fid:
                serialized_graph = fid.read()
                od_graph_def.ParseFromString(serialized_graph)
                tf.import_graph_def(od_graph_def, name='')
            self.sess = tf.compat.v1.Session(graph=self.detection_graph)
        self.image_tensor = self.detection_graph.get_tensor_by_name('image_tensor:0')
        self.detection_boxes = self.detection_graph.get_tensor_by_name('detection_boxes:0')
        self.detection_scores = self.detection_graph.get_tensor_by_name('detection_scores:0')
        self.detection_classes = self.detection_graph.get_tensor_by_name('detection_classes:0')
        self.num_detections = self.detection_graph.get_tensor_by_name('num_detections:0')

    def close(self):
        self.sess.close()

    def device_info(self):
        try:
            return [device.name for device in tf.config.list_logical_devices()]
        except Exception as error:
            return ["TensorFlow device lookup failed: {}".format(error)]

    def detect_tile(self, image_bgr, ids, imR, imC, xdim, ydim):
        imW = image_bgr.shape[1]
        imH = image_bgr.shape[0]
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image_expanded = np.expand_dims(image_rgb, axis=0)
        boxes, scores, classes, num = self.sess.run(
            [self.detection_boxes, self.detection_scores, self.detection_classes, self.num_detections],
            feed_dict={self.image_tensor: image_expanded},
        )
        boxes = np.squeeze(boxes)
        score = np.squeeze(scores)
        classes = np.squeeze(classes).astype(np.int32)
        raw_count = int(num[0]) if np.ndim(num) > 0 else int(num)
        tree_list = []
        filtered_count = 0
        for i in range(boxes.shape[0]):
            if score is None or score[i] > DETECTION_CONFIDENCE_THRESHOLD:
                filtered_count += 1
                ids = ids + 1
                boxes1 = tuple(boxes[i].tolist())

                if classes[i] in six.viewkeys(self.category_index):
                    self.category_index[classes[i]]['name']

                ymin, xmin, ymax, xmax = boxes1
                ymin = int(ymin * imH)
                xmin = int(xmin * imW)
                ymax = int(ymax * imH)
                xmax = int(xmax * imW)
                mox = round((xmin + xmax) / 2, 2)
                moy = round((ymin + ymax) / 2, 2)

                objects = {"ids": ids,
                            "score": float(score[i]),
                            "x_coordinate": mox + xdim,
                            "y_coordinate": moy + ydim,
                            "xmin": xmin + xdim,
                            "ymin": ymin + ydim,
                            "xmax": xmax + xdim,
                            "ymax": ymax + ydim,
                            "row": imR,
                            "column": imC,
                            "heigth": imH,
                            "width": imW}

                tree_list.append(objects)
        return tree_list, raw_count, filtered_count


def create_detector():
    detector = PalmOilTreeDetector()
    detector.backend_name = "faster_rcnn"
    return detector


def iter_image_tiles(image):
    img_shape = image.shape
    for row in range(int(math.ceil(img_shape[0] / (TILE_OFFSET[1] * 1.0)))):
        for column in range(int(math.ceil(img_shape[1] / (TILE_OFFSET[0] * 1.0)))):
            y1 = TILE_OFFSET[1] * row
            y2 = min(TILE_OFFSET[1] * row + TILE_SIZE[1], img_shape[0])
            x1 = TILE_OFFSET[0] * column
            x2 = min(TILE_OFFSET[0] * column + TILE_SIZE[0], img_shape[1])
            cropped_img = image[y1:y2, x1:x2]
            if (x2 - x1) > 33 and (y2 - y1) > 33:
                yield row, column, x1, y1, cropped_img


def run_detection_on_image(image_path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError("Unable to read image file: {}".format(image_path))
    detector = create_detector()
    list_coordinates = []
    raw_count = 0
    filtered_count = 0
    tile_count = 0
    try:
        device_info = detector.device_info()
        for row, column, x_offset, y_offset, tile in iter_image_tiles(image):
            tile_count += 1
            data_list, tile_raw_count, tile_filtered_count = detector.detect_tile(
                tile,
                len(list_coordinates),
                row,
                column,
                x_offset,
                y_offset,
            )
            raw_count += tile_raw_count
            filtered_count += tile_filtered_count
            list_coordinates.extend(data_list)
    finally:
        detector.close()
    debug_metadata = {
        "detection_image_path": str(image_path),
        "detection_image_width": int(image.shape[1]),
        "detection_image_height": int(image.shape[0]),
        "tile_count": tile_count,
        "raw_detections": raw_count,
        "confidence_filtered_detections": filtered_count,
        "coordinate_filtered_detections": 0,
        "detector_devices": device_info,
        "tensorflow_devices": device_info,
    }
    return image.shape, list_coordinates, debug_metadata


def palmoil_tree_detection(images_file, ids, imR, imC, xdim, ydim):
    image = cv2.imread(str(images_file))
    if image is None:
        raise FileNotFoundError("Unable to read image file: {}".format(images_file))
    detector = create_detector()
    try:
        tree_list, raw_count, filtered_count = detector.detect_tile(image, ids, imR, imC, xdim, ydim)
        return image, tree_list
    finally:
        detector.close()

  
def process_even(even_list, csv_path, img_offset):
    """
    function to print square of given num
    """
    offset = img_offset
    list_coordinates = []
    xcounters = 0
    ycounters = 0
    ids = 0
    print ('Process_Even: Starting')
    for i in even_list:
        test = i.split("/")[-1].split('_')[-1].split(".")[0].replace("c","")
        print(test)
        r=int(i.split("/")[-1].split('_')[-2].replace("r",""))
        c=int(i.split("/")[-1].split('_')[-1].split(".")[0].replace("c",""))
        img, data_list = palmoil_tree_detection(str(i),ids+len(list_coordinates),r,c, xcounters+c*offset[0], ycounters+r*offset[1])
        for tree in data_list:
            print("Prcessing Coordinate In Process_Even")
            list_coordinates.append(tree)
    data = DataFrame(list_coordinates, columns=DETECTION_COLUMNS)
    # save as csv.
    data.to_csv(csv_path +"/"+"DATA_even.csv", index=False)
    print(" Process_Even: End")
  

def process_odd(odd_list, csv_path, img_offset):
    """
    function to print square of given num
    """
    offset = img_offset
    list_coordinates = []
    xcounters = 0
    ycounters = 0
    ids = 0
    print ('Process_Odd: Starting')
    for i in odd_list:
        test = i.split("/")[-1].split('_')[-1].split(".")[0].replace("c","")
        print(test)
        r=int(i.split("/")[-1].split('_')[-2].split("r")[1])
        c=int(i.split("/")[-1].split('_')[-1].split(".")[0].replace("c",""))
        img, data_list = palmoil_tree_detection(str(i),ids+len(list_coordinates),r,c, xcounters+c*offset[0], ycounters+r*offset[1])
        for tree in data_list:
            print("Prcessing Coordinate In Process_Odd")
            list_coordinates.append(tree)
    data = DataFrame(list_coordinates, columns=DETECTION_COLUMNS)
    # save as csv.
    data.to_csv(csv_path+"/"+"DATA_odd.csv", index=False)
    print('Process_Odd: End')
            
def main(image_file, Timestamp, __name__, base_path=None, return_debug=False):
    if __name__ == '__main__':
        start = time.perf_counter()
        # 1. get current working directory
        BASE_DIR = Path(__file__).resolve().parent.parent
        MAIN_PATH = base_path or os.path.join(BASE_DIR, "frontend/src/imageFile/")
        path_create = os.path.join(str(MAIN_PATH) ,'media')
        ismedia = os.path.isdir(path_create)
        
        if ismedia == False:
            os.mkdir(path_create)
            print("Done Created" + str(path_create))
        else:
            print("Already Created") 
            pass
        
        listmedia = os.listdir(path_create)
        if len(listmedia)>0:
            for media in listmedia:
                media_path = os.path.join(str(path_create), media)
                print(media)
                if os.path.isdir(media_path):
                    safe_rmtree(media_path)

        # 2. make directory to store process (images_folder, csv_folder, merged_csv)
        Timestamp = Timestamp
        # 3. make process folder 
        Process_folder = os.path.join(str(path_create), str(image_file)+"_"+str(Timestamp))
        isdir_1 = os.path.isdir(Process_folder)
        
        if isdir_1 == False:
            os.mkdir(Process_folder)
            print("Done Created" + str(Process_folder))
        else:
            print("Already created") 
            pass
        # 3. make images_folder, csv_folder inside process_folder
        images_folder = os.path.join(str(Process_folder), "tiling_images")
        csv_folder = os.path.join(str(Process_folder), "csv_data")

        isdir_2 = os.path.isdir(images_folder)
        isdir_3 = os.path.isdir(csv_folder)
        if isdir_2 == False and isdir_3 == False:
            os.mkdir(images_folder)
            os.mkdir(csv_folder)
            print("Done Created" + str(images_folder))
            print("Done Created" + str(csv_folder))
        else:
            print("Already created") 
            pass

        image_path = str(image_file)
        if not os.path.isabs(image_path):
            image_path = os.path.join(str(MAIN_PATH), image_path)
        if not os.path.exists(image_path):
            image_path = os.path.join(str(path_create), str(image_file))
        print(image_path)
        img_shape, merged_rows, debug_metadata = run_detection_on_image(image_path)

        print ('Coordinate_Filtering: Starting')
        if not merged_rows:
            safe_rmtree(Process_folder)
            finish = time.perf_counter()
            debug_metadata["coordinate_filtered_detections"] = 0
            debug_metadata["runtime_seconds"] = round(finish - start, 2)
            print ('Coordinate_Filtering: End')
            print("Done!:", finish)
            return ([], debug_metadata) if return_debug else []

        merged_rows = sorted(merged_rows, key=lambda row: float(row.get("score") or 0), reverse=True)
        duplicate_point_distance = duplicate_point_distance_for_image(img_shape)
        debug_metadata["duplicate_point_distance"] = duplicate_point_distance
        new_merge, merged_cluster_count = merge_duplicate_detections(merged_rows, duplicate_point_distance)
        debug_metadata["merged_duplicate_clusters"] = merged_cluster_count
        debug_metadata["duplicate_filtered_detections"] = len(new_merge)
        
         # 3. Uniq
        result = [[x["x_coordinate"], x["y_coordinate"]] for x in new_merge]
        if not result:
            safe_rmtree(Process_folder)
            finish = time.perf_counter()
            debug_metadata["coordinate_filtered_detections"] = 0
            debug_metadata["runtime_seconds"] = round(finish - start, 2)
            print ('Coordinate_Filtering: End')
            print("Done!:", finish)
            return ([], debug_metadata) if return_debug else []
        filtered = np.unique(result, axis=0)
        filtered = filtered.tolist()
        debug_metadata["unique_coordinate_detections"] = len(filtered)
        rows = [x for x in filtered]
        rows = [[float(x[0]),float(x[1])] for x in rows]
        sort = sorted(rows, key = lambda x: (float(x[1]), float(x[0]))) ##
        sort = [ (float(x[0]), float(x[1])) for x in sort] ##
        
        new_sorted = list([])
        row_amt = math.trunc(img_shape[0]/58)
        for row in get_rows(sort, row_amt, int(img_shape[0])):
            new_sorted.append(row)
            
        db_data =[]  
        for i in new_sorted:
            for j in i:
                db_data.append(j)
        debug_metadata["row_grouped_detections"] = len(db_data)

                
        temp_data = []
        for temp in db_data:
            item = {"lat":-float(temp[1])+img_shape[0], ##
                    "lng":float(temp[0]) ##
                    }
            temp_data.append(item)
                
        safe_rmtree(Process_folder)
        finish = time.perf_counter()
        debug_metadata["coordinate_filtered_detections"] = len(temp_data)
        debug_metadata["runtime_seconds"] = round(finish - start, 2)
        print ('Coordinate_Filtering: End')
        print("Done!:", finish)
        return (temp_data, debug_metadata) if return_debug else temp_data

