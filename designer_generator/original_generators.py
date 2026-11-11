"""Unmodified generator cell 54 from EastC0ast/lab01, generator @ 01a1c6ce89d076e969bf0a8300fcd9abc2c96e36."""
import numpy as np

def generate_knuth(n_samples, a_param, loc, scale):
    generated = []
    attempts = 0
    while len(generated) < n_samples:
        attempts += 1
        u1 = np.random.rand()
        y = np.tan(np.pi * u1)

        x_cand = np.sqrt(2 * a_param - 1) * y + a_param - 1
    
        if x_cand <= 0:
            continue
            
        v = np.random.rand()
        condition = (1 + y**2) * np.exp((a_param - 1) * np.log(x_cand / (a_param - 1)) - np.sqrt(2 * a_param - 1) * y)
        
        if v <= condition:
            x_final = loc + scale * x_cand
            generated.append(x_final)
            
    return np.array(generated)[:n_samples], attempts
    
def generate_gd(n_samples, a, loc, scale):
    generated = []
    attempts = 0
    
    s2 = a - 0.5
    s = np.sqrt(s2)
    d = 5.65685424949238 - 12 * s
    
    q0 = 1 / (24 * a) + 1 / (48 * a**2) + 23 / (2880 * a**3)
    
    while len(generated) < n_samples:
        attempts += 1
        t = np.random.normal()
        x_base = s + t / 2
        x2 = x_base * x_base
        
        if t >= 0:
            x_final = loc + scale * (2 * a - x2)
            generated.append(x_final)
            continue
            
        u = np.random.rand()
        if d * u <= t**3:
            x_final = loc + scale * (2 * a - x2)
            generated.append(x_final)
            continue
            
        if x_base <= 0:
            continue
            
        v = t / (s + s)
        if np.abs(v) > 0.25:
            q = q0 - s * t + (t**2) / 4 + (s2 + s2) * np.log(1 + v)
        else:
            q = q0 + (t**2 / 2) * (0.33333333 * v - 0.25 * v**2 + 0.2 * v**3)
            
        if np.log(1 - u) <= q:
            x_final = loc + scale * (2 * a - x2)
            generated.append(x_final)
            
    return np.array(generated)[:n_samples], attempts
