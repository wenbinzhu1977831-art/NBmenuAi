import re

with open(r'c:\Users\wenbi\OneDrive\桌面\Gemini 3 Live API\frontend\src\App.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Locate the right column exact boundaries
start_idx = text.find('                 {/* Right Column: Charts & Live Transcript (Span 9 now) */}')
if start_idx == -1:
    print("Cannot find right column start")
    exit(1)

# Find the end of this block
#                 </div>
#              </div>
#            )}
#
#            {/* ---- TAB: AI BRAIN ---- */}
end_idx = text.find('            {/* ---- TAB: AI BRAIN ---- */}')
if end_idx == -1:
    print("Cannot find right column end")
    exit(1)

# we only replace between start_idx and the ending div of right col
sub_text = text[start_idx:end_idx]

# Extract the two blocks
charts_pattern = re.compile(r'(?:[ \t]*\{\/\* ---- STATS CHARTS ROW ---- \*\/\}.*?)(?=[ \t]*\{\/\* ---- LIVE TRANSCRIPT ROW ---- \*\/\})', re.DOTALL)
transcript_pattern = re.compile(r'(?:[ \t]*\{\/\* ---- LIVE TRANSCRIPT ROW ---- \*\/\}.*?(?=\n[ \t]*<\/div>\n[ \t]*<\/div>\n[ \t]*\{\/\* ---- TAB: AI BRAIN ---- \*\/\})|(?:\n[ \t]*<\/div>\n[ \t]*<\/div>\n$)))', re.DOTALL)

# Because sub_text is a chunk, let's just search in sub_text
charts_match = charts_pattern.search(sub_text)
# For transcript, look for everything after "---- LIVE TRANSCRIPT ROW ----" up to the end of the col-span-9 div
transcript_match = re.search(r'[ \t]*\{\/\* ---- LIVE TRANSCRIPT ROW ---- \*\/\}.*?(?=\n[ \t]*<\/div>\n[ \t]*<\/div>\n$)', sub_text, re.DOTALL)

if charts_match and transcript_match:
    charts_block = sub_text[charts_match.start():charts_match.end()]
    transcript_block = sub_text[transcript_match.start():transcript_match.end()]
    
    # Let's rebuild the right column
    # Add lg:flex-row to the top div
    new_sub = sub_text[:charts_match.start()]
    new_sub = new_sub.replace('<div className="lg:col-span-9 flex flex-col gap-6">', '<div className="lg:col-span-9 flex flex-col lg:flex-row gap-6 h-full min-h-0">')
    
    # Modify transcript block to be on the left and take remaining space
    transcript_mod = transcript_block.replace('<div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col flex-1 min-h-[400px]">', '<div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col flex-1 min-w-0 h-full">')
    
    # Modify charts block: change the grid to be a vertical flex column
    charts_mod = charts_block.replace('<div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-64">', '<div className="flex flex-col gap-6 w-full lg:w-[35%] xl:w-[30%] shrink-0 h-full overflow-y-auto right-pane-scrollbar">')
    charts_mod = charts_mod.replace('<Card title=', '<Card className="min-h-[250px] flex-1 flex flex-col" title=')
    
    # Swap order: transcript first, then charts
    new_sub += transcript_mod + '\n\n' + charts_mod + '\n                 </div>\n              </div>\n'
    
    # Replace in origin text
    new_text = text[:start_idx] + new_sub + text[end_idx:]
    
    with open(r'c:\Users\wenbi\OneDrive\桌面\Gemini 3 Live API\frontend\src\App.jsx', 'w', encoding='utf-8') as f:
        f.write(new_text)
    print("Success")
else:
    print("Failed to find blocks correctly")
