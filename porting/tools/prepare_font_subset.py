"""Derive a private Latin/Greek/Cyrillic subset; verify every retained outline and advance."""
import hashlib,json,sys,zlib
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'toolchain/python'))
from fontTools import subset,__version__
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=P/'analysis/candidate-sd/assets/published/fonts/Ascender_Uni.ttf'
    root=P/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace/test-output/font-subset';root.mkdir(parents=True,exist_ok=True)
    target=root/source.name;original=TTFont(source,recalcTimestamp=False);cmap=original.getBestCmap()
    ranges=((0,0x24f),(0x370,0x52f),(0x2000,0x206f),(0x20a0,0x20cf),(0x2100,0x22ff),(0x2500,0x26ff),(0xe000,0xe0ff),(0xfffd,0xfffd))
    keep={cp for cp in cmap if any(a<=cp<=b for a,b in ranges)}
    assert set(range(0x20,0x7f))<=keep
    options=subset.Options();options.recalc_timestamp=False;options.recalc_bounds=False
    options.glyph_names=True;options.notdef_glyph=True;options.notdef_outline=True;options.recommended_glyphs=True
    font=TTFont(source,recalcTimestamp=False);s=subset.Subsetter(options=options);s.populate(unicodes=keep);s.subset(font);font.recalcBBoxes=False;font.save(target)
    derived=TTFont(target,recalcTimestamp=False);dc=derived.getBestCmap();assert set(dc)==keep
    og,dg=original.getGlyphSet(),derived.getGlyphSet()
    for cp in sorted(keep):
        a,b=cmap[cp],dc[cp];assert original['hmtx'][a]==derived['hmtx'][b],cp
        pa,pb=DecomposingRecordingPen(og),DecomposingRecordingPen(dg);og[a].draw(pa);dg[b].draw(pb);assert pa.value==pb.value,cp
    assert original['head'].unitsPerEm==derived['head'].unitsPerEm
    assert (original['hhea'].ascent,original['hhea'].descent,original['hhea'].lineGap)==(derived['hhea'].ascent,derived['hhea'].descent,derived['hhea'].lineGap)
    report={'source_sha256':sha(source),'source_bytes':source.stat().st_size,'source_glyphs':original['maxp'].numGlyphs,
        'subset_sha256':sha(target),'subset_bytes':target.stat().st_size,'subset_crc32':f'{zlib.crc32(target.read_bytes()):08x}',
        'subset_glyphs':derived['maxp'].numGlyphs,'codepoints':sorted(keep),'outlines_and_advances_verified':len(keep),
        'fonttools_version':__version__,'original_unchanged':True,'font_files_published':False,'languages_scope':'Retain available Latin/Greek/Cyrillic; CJK excluded; missing source glyphs are not invented',
        'cyrillic_codepoints_kept':sum(0x400<=cp<=0x52f for cp in keep)}
    assert sha(source)==report['source_sha256'] and target.stat().st_size<source.stat().st_size//10
    (P/'analysis/font-subset-contract.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Font subset:',report['source_bytes'],'->',report['subset_bytes'],'bytes;',report['outlines_and_advances_verified'],'outlines and metrics identical')
if __name__=='__main__':main()
