import numpy as np

def smoothstep(edge0, edge1, x):
    x = np.clip((x - edge0) / (edge1 - edge0), 0, 1)
    return x * x * (3.0 - 2.0 * x)
