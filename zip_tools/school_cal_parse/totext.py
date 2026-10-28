import re,html,sys,subprocess,os
def text(f):
    b=open(f,'rb').read()
    if b[:4]==b'%PDF':
        return subprocess.run(['pdftotext','-layout',f,'-'],capture_output=True,text=True).stdout
    s=b.decode('utf-8','ignore')
    s=re.sub(r'(?is)<script.*?</script>|<style.*?</style>|<nav.*?</nav>','',s)
    s=re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|h\d)>','\n',s)
    s=re.sub(r'(?i)</t[dh]>',' | ',s)
    t=html.unescape(re.sub(r'<[^>]+>',' ',s))
    t=re.sub(r'[ \t\xa0]+',' ',t); t=re.sub(r'\n\s*\n+','\n',t)
    return t
if __name__=='__main__':
    for f in sys.argv[1:]:
        t=text(f); open(os.path.splitext(f)[0]+'.txt','w').write(t)
