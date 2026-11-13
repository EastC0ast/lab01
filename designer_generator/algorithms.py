"""Gamma samplers from uniform/normal primitives, using independent RNG objects.

A: Knuth, The Art of Computer Programming, vol. 2, section 3.4.1, algorithm A.
GD: Ahrens & Dieter (1982), doi:10.1145/358315.358390. The polynomial
coefficients and all three acceptance stages are specified by that algorithm.
The R GammaDist reference documents an independent production implementation:
https://stat.ethz.ch/R-manual/R-devel/library/stats/html/GammaDist.html
This module is an independently written Python implementation of the method.
"""

import math
import numpy as np


def _polynomial_without_constant(z, coefficients):
    result = 0.
    for coefficient in reversed(coefficients):
        result = z * (coefficient + result)
    return result


def _positive_uniform(rng):
    value = rng.random()
    while value == 0:
        value = rng.random()
    return value


def gamma_a(n, a, rng):
    """Knuth A, for a > 1: Cauchy proposal followed by rejection."""
    if not isinstance(n, int) or n < 1 or not math.isfinite(a) or a <= 1:
        raise ValueError('A requires a positive integer n and a > 1.')
    values = np.empty(n)
    coefficient = math.sqrt(2*a - 1)
    completed = proposals = uniforms = 0
    while completed < n:
        proposals += 1
        uniforms += 1
        tangent = math.tan(math.pi * rng.random())
        candidate = a - 1 + coefficient*tangent
        if candidate <= 0:
            continue
        uniforms += 1
        log_acceptance = (math.log1p(tangent*tangent)
                          + (a-1)*math.log(candidate/(a-1)) - coefficient*tangent)
        if math.log(_positive_uniform(rng)) <= log_acceptance:
            values[completed] = candidate
            completed += 1
    return values, {'proposals': proposals, 'uniforms': uniforms, 'normals': 0, 'hat_proposals': 0}


def gamma_gd(n, a, rng):
    """Full Ahrens--Dieter GD, a >= 1, including the exponential hat stage."""
    if not isinstance(n, int) or n < 1 or not math.isfinite(a) or a < 1:
        raise ValueError('GD requires a positive integer n and a >= 1.')
    s2 = a-.5
    s = math.sqrt(s2)
    squeeze = math.sqrt(32)-12*s
    q0 = _polynomial_without_constant(1/a,
          (.04166669, .02083148, .00801191, .00144121, -.00007388, .00024511, .0002424))
    quotient_coefficients = (.3333333, -.250003, .2000062, -.1662921, .1423657, -.1367177, .1233795)
    if a <= 3.686:
        center, laplace_scale, envelope = .463+s+.178*s2, 1.235, .195/s-.079+.16*s
    elif a <= 13.022:
        center, laplace_scale, envelope = 1.654+.0076*s2, 1.68/s+.275, .062/s+.024
    else:
        center, laplace_scale, envelope = 1.77, .75, .1515/s

    def quotient(t):
        v = t/(2*s)
        if abs(v) <= .25:
            return q0 + .5*t*t*_polynomial_without_constant(v, quotient_coefficients)
        return q0 - s*t + .25*t*t + 2*s2*math.log1p(v)

    values = np.empty(n)
    proposals = uniforms = normals = hats = 0
    for i in range(n):
        normals += 1
        proposals += 1
        t = float(rng.standard_normal())
        root = s + .5*t
        accepted = t >= 0
        if not accepted:
            uniforms += 1
            u = rng.random()
            accepted = squeeze*u <= t*t*t
            if not accepted and root > 0:
                accepted = math.log1p(-u) <= quotient(t)
        if not accepted:
            # Rejected normal candidates are replaced by the exponential hat,
            # not by restarting normal sampling. This stage supplies the tail.
            while True:
                hats += 1
                proposals += 1
                uniforms += 2
                exponential = -math.log(_positive_uniform(rng))
                signed_uniform = 2*rng.random()-1
                t = center + math.copysign(laplace_scale*exponential, signed_uniform)
                if t < -.71874483771719:
                    continue
                q = quotient(t)
                if q <= 0:
                    continue
                # log(expm1(q)) is evaluated without overflow for large q.
                log_w = math.log(math.expm1(q)) if q < 50 else q + math.log1p(-math.exp(-q))
                left = -math.inf if signed_uniform == 0 else math.log(envelope*abs(signed_uniform))
                if left <= log_w + exponential - .5*t*t:
                    root = s + .5*t
                    break
        values[i] = root*root
    return values, {'proposals': proposals, 'uniforms': uniforms, 'normals': normals, 'hat_proposals': hats}
