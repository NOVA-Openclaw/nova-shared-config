import json,subprocess

# direct -> openrouter mirror map (verified present in registry)
ORM = {
 "anthropic/claude-opus-5":"openrouter/anthropic/claude-opus-5",
 "anthropic/claude-opus-4.8":"openrouter/anthropic/claude-opus-4.8",
 "anthropic/claude-sonnet-5":"openrouter/anthropic/claude-sonnet-5",
 "anthropic/claude-sonnet-4.6":"openrouter/anthropic/claude-sonnet-4.6",
 "anthropic/claude-sonnet-4.5":"openrouter/anthropic/claude-sonnet-4.5",
 "anthropic/claude-fable-5":"openrouter/anthropic/claude-fable-5",
 "anthropic/claude-haiku-4.5":"openrouter/anthropic/claude-haiku-4.5",
 "google/gemini-3.5-flash":"openrouter/google/gemini-3.5-flash",
 "deepseek/deepseek-v4-pro":"openrouter/deepseek/deepseek-v4-pro",
 "deepseek/deepseek-v4-flash":"openrouter/deepseek/deepseek-v4-flash",
 "xai/grok-4.5":"openrouter/x-ai/grok-4.5",
 "xai/grok-4.3":"openrouter/x-ai/grok-4.3",
 "moonshot/kimi-k2.7-code":"openrouter/moonshotai/kimi-k2.7-code",
 "moonshot/kimi-k2.6":None,   # no OR mirror
 "openrouter/moonshotai/kimi-k3":"__SOLO__",  # OR-only, no direct
}
def pair(m):
    o=ORM.get(m,"__UNKNOWN__")
    if o=="__UNKNOWN__": raise SystemExit("unmapped model: "+m)
    if o=="__SOLO__": return [m]
    return [m] if o is None else [m,o]

# version-descent ladders (same family, newest->oldest)
SONNET=["anthropic/claude-sonnet-5","anthropic/claude-sonnet-4.6","anthropic/claude-sonnet-4.5"]
OPUS  =["anthropic/claude-opus-5","anthropic/claude-opus-4.8"]
FABLE =["anthropic/claude-fable-5"]
GEM   =["google/gemini-3.5-flash"]
DSF   =["deepseek/deepseek-v4-flash"]
DSP   =["deepseek/deepseek-v4-pro"]
GROK45=["xai/grok-4.5"]; GROK43=["xai/grok-4.3"]
KIMI  =["moonshot/kimi-k2.7-code","moonshot/kimi-k2.6"]
KIMI3 =["openrouter/moonshotai/kimi-k3","moonshot/kimi-k2.7-code","moonshot/kimi-k2.6"]

def build(ladder, tail, local):
    out=[]
    for m in ladder: out+=pair(m)
    for fam in tail:
        for m in fam: out+=pair(m)
    out.append(local)
    return out

SONNET_TIER = build(SONNET,[GROK43,GEM,DSF],"ollama/qwen2.5:14b")
SONNET_CODER= build(SONNET,[GROK43,GEM,DSF],"ollama/qwen2.5-coder:14b")
GEMINI_TIER = build(GEM,[SONNET,DSF],"ollama/qwen2.5:14b")
FABLE_TIER  = build(FABLE,[OPUS,GROK45,DSP],"ollama/qwen2.5:32b")

AGENTS={
 "athena":SONNET_TIER,"bastion":SONNET_TIER,"cadence":SONNET_TIER,"cyrus":SONNET_TIER,
 "flint":SONNET_TIER,"gallan":SONNET_TIER,"hadrian":SONNET_TIER,"hermes":SONNET_TIER,
 "maren":SONNET_TIER,"scribe":SONNET_TIER,"swift":SONNET_TIER,
 "gem":SONNET_CODER,"gidget":SONNET_CODER,
 "ember":GEMINI_TIER,"flicker":GEMINI_TIER,"grain":GEMINI_TIER,"sage":GEMINI_TIER,
 "tide":GEMINI_TIER,"yield":GEMINI_TIER,
 "scout":build(GEM,[SONNET,GROK43,DSF],"ollama/qwen2.5:14b"),
 "lex":build(SONNET,[GROK43,GEM,["anthropic/claude-haiku-4.5"]],"ollama/qwen2.5:14b"),
 "iris":FABLE_TIER,"quill":FABLE_TIER,
 "marcie":build(DSF,[KIMI,GEM],"ollama/qwen2.5:14b"),
 "coder":build(KIMI,[SONNET,GEM],"ollama/qwen2.5-coder:14b"),
 "pixel":build(KIMI3,[SONNET,GEM],"ollama/qwen2.5-coder:14b"),
 "ticker":build(GROK45,[GEM,DSF],"ollama/qwen2.5:14b"),
}
PRIMARY={"iris":"anthropic/claude-fable-5","quill":"anthropic/claude-fable-5"}

def lit(a): return "{"+",".join(a)+"}"
sql=[]
for n,ch in sorted(AGENTS.items()):
    p=PRIMARY.get(n)
    if p and ch and ch[0]==p:
        ch=ch[1:]                      # primary must not repeat as fallback #1
        AGENTS[n]=ch
    assert not p or ch[0]!=p, n
    if p: sql.append("UPDATE agents SET model='%s', fallback_models='%s' WHERE name='%s';"%(p,lit(ch),n))
    else: sql.append("UPDATE agents SET fallback_models='%s' WHERE name='%s';"%(lit(ch),n))
sql.append("UPDATE agents SET model=NULL, fallback_models=NULL WHERE name IN ('graybeard','newhart','victoria');")
open("/tmp/nova-chains.sql","w").write("BEGIN;\n"+"\n".join(sql)+"\nCOMMIT;\n")
for n,ch in sorted(AGENTS.items()):
    print(n,"| primary:",PRIMARY.get(n,"(unchanged)"))
    for i,m in enumerate(ch,1): print("   ",i,m)
