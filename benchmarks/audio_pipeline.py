"""Cost of the audio cleanup chain on a 30-second take.

Run from the repo root:  python benchmarks/audio_pipeline.py

Also checks the vectorized high-pass filter against a plain per-sample loop, so the
speed-up is shown to produce the same output, not just faster output.
"""
import sys,os,time; sys.path.insert(0,os.getcwd())
import numpy as np
from audio import preprocessor as p, vad
rng=np.random.default_rng(0); a=(rng.standard_normal(16000*30)*0.05).astype(np.float32)
def best(f,n=5):
    ts=[]; 
    for _ in range(n): t=time.perf_counter(); f(); ts.append(time.perf_counter()-t)
    return min(ts)*1000
def loop_hpf(x,sr=16000,fc=80.0):
    rc=1/(2*np.pi*fc); dt=1/sr; al=rc/(rc+dt); y=np.empty_like(x); y[0]=x[0]
    for i in range(1,len(x)): y[i]=al*(y[i-1]+x[i]-x[i-1])
    return y
L=best(lambda:loop_hpf(a),1); V=best(lambda:p.high_pass_filter(a))
print(f"HPF 30s: loop {L:.0f} ms, vectorized {V:.2f} ms ({L/V:.0f}x), max diff {np.abs(loop_hpf(a)-p.high_pass_filter(a)).max():.1e}")
print(f"clean chain 30s: {best(lambda:p.clean_speech_audio(a,16000,0.5)):.1f} ms")
print(f"normalize 30s: {best(lambda:p.normalize_audio(a)):.1f} ms")
vad.warm_up(); print(f"VAD trim 30s: {best(lambda:vad.trim_to_speech(a,16000),3):.0f} ms")
