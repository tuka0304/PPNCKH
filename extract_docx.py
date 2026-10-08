import docx2txt

with open('extract.txt', 'w', encoding='utf-8') as f:
    f.write('--- Thống kê dl VT.docx ---\n')
    f.write(docx2txt.process('Thống kê dl VT.docx'))
    f.write('\n\n--- Các loại Bieu_do_LST_NDVI_TVDI.docx ---\n')
    f.write(docx2txt.process('Các loại Bieu_do_LST_NDVI_TVDI.docx'))
