import argparse
import time

import cv2
import numpy as np
import pynput.mouse

from gest.cv_gui import text
from gest.inference import InferenceSession


parser = argparse.ArgumentParser()
parser.add_argument("model_file", help="Model file")
parser.add_argument("--camera", help="Camera index", type=int, default=0)
parser.add_argument("--fps-limit", help="Frames per second limit", type=int)
parser.add_argument("--sensitivity", help="Scrolling sensitivity", type=int, default=15)


def relative_average_y(heatmap, weight_exponent):
    weights = heatmap.sum(axis=1) ** weight_exponent
    y, step = np.linspace(0, 1, weights.shape[0], endpoint=False, retstep=True)
    y += step / 2
    return (y * weights).sum() / weights.sum()


def accumulate(accumulated, current, accumulated_weight):
    if accumulated is None:
        return current
    return (accumulated * accumulated_weight + current) / (accumulated_weight + 1)


class App:

    def __init__(self, camera, model_file, fps_limit, scrolling_sensitivity):
        self.camera = camera
        self.inference_session = InferenceSession(model_file)
        self.mouse = pynput.mouse.Controller()

        self.fps_limit = fps_limit
        self.scrolling_sensitivity = scrolling_sensitivity

    def run(self):
        capture = cv2.VideoCapture(self.camera)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        acc_score = None
        acc_relative_y = None
        root_relative_y = None
        on = False
        last_time = None
        while True:
            ret, frame = capture.read()
            if not ret:
                break

            # fps limiting
            this_time = time.time()
            if self.fps_limit and last_time and (this_time - last_time) * self.fps_limit < 1:
                continue

            # inference
            heatmap = self.inference_session.cv2_run(frame)

            # scrolling state on/off
            score = heatmap.max()
            acc_score = accumulate(acc_score, score, accumulated_weight=3)
            if on and acc_score < .2:
                on = False
                acc_relative_y = None
                root_relative_y = None
            if not on and acc_score > .5:
                on = True

            if on:
                # update current y-position selection
                if score > .2:
                    relative_y = relative_average_y(heatmap, weight_exponent=4)
                    if root_relative_y is None:
                        root_relative_y = relative_y
                    acc_relative_y = accumulate(acc_relative_y, relative_y,
                                                accumulated_weight=3)

                # draw root and current y selection
                frame[int(root_relative_y * frame.shape[0]), :] = [0, 255, 0]
                frame[int(acc_relative_y * frame.shape[0]), :] = [0, 0, 255]

                # scroll
                self.mouse.scroll(0, int(
                    self.scrolling_sensitivity * (root_relative_y - acc_relative_y)
                ))
            cv2.imshow('Camera', text(cv2.flip(frame, 1), "Press ESC to quit"))
            if cv2.waitKey(1) & 0xFF == 27:  # esc to quit
                break
            last_time = this_time

        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    args = parser.parse_args()
    App(
        camera=args.camera,
        model_file=args.model_file,
        fps_limit=args.fps_limit,
        scrolling_sensitivity=args.sensitivity,
    ).run()