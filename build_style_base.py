"""The clean cut every style version starts from: tightened, L2, graded,
NO captions and NO graphics. One framing throughout, so each style is free
to add its own motion."""
import json, subprocess
R="/Users/georgegeddes/Library/Application Support/Claude/scratch-workspaces/6d38ae6d-05dd-4827-8e46-76304910d38e/68f1a3b0-a8d1-4d98-a822-3205d41bec7a/scratch-2026-10-28-f045e2"
import glob
SRC=glob.glob(f"{R}/jobs/fns-2905408276/clips_1080/08_*.mp4")[0]
keeps=json.load(open("/tmp/keeps.json"))

# pass 1 — concat the keeps into a clean 16:9 cut
parts=[]
for i,(a,b) in enumerate(keeps):
    parts.append(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[v{i}]")
    parts.append(f"[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS[a{i}]")
cc="".join(f"[v{i}][a{i}]" for i in range(len(keeps)))
fg=";".join(parts)+f";{cc}concat=n={len(keeps)}:v=1:a=1[v][a]"
subprocess.run(["ffmpeg","-y","-v","error","-i",SRC,"-filter_complex",fg,
                "-map","[v]","-map","[a]","-c:v","libx264","-crf","16","-preset","fast",
                "-pix_fmt","yuv420p","-c:a","pcm_s16le",f"{R}/renders/styles/_cut169.mov"],check=True)
print("pass 1: clean 16:9 cut")

# pass 2 — L2: facecam over content, graded on the face only
SEAM=806
fg2=(
 # facecam 464x262 @1456,818 -> fill 1080x806
 f"[0:v]crop=464:262:1456:818,scale=1427:806:flags=lanczos,crop=1080:806:174:0,"
 f"eq=contrast=1.06:saturation=1.18:gamma=1.02[cam];"
 # content 1920x988 @0,92 -> fill 1080x1114, centred
 f"[0:v]crop=1920:988:0:92,scale=2165:1114:flags=lanczos,crop=1080:1114:543:0[doc];"
 f"[cam][doc]vstack=2[v]"
)
subprocess.run(["ffmpeg","-y","-v","error","-i",f"{R}/renders/styles/_cut169.mov",
                "-filter_complex",fg2,"-map","[v]","-map","0:a",
                "-c:v","libx264","-crf","16","-preset","fast","-pix_fmt","yuv420p",
                "-c:a","pcm_s16le",f"{R}/renders/styles/_base.mov"],check=True)
print("pass 2: L2 base")
