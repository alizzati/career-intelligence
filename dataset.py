import os
from datasets import load_dataset



# 1. Muat dataset dari Hugging Face
ds = load_dataset("AzharAli05/Resume-Screening-Dataset")
#https://huggingface.co/datasets/AzharAli05/Resume-Screening-Dataset

# 2. Buat folder untuk menyimpan file PDF (jika belum ada)
output_dir = "downloaded_resumes"
os.makedirs(output_dir, exist_ok=True)

# 3. Tentukan berapa banyak resume yang mau diunduh (contoh: 5 resume pertama)
num_to_download = 5

# 4. Ambil split data (biasanya 'train')
data_split = ds["train"]

print(f"Mengunduh {num_to_download} resume...")

for i in range(min(num_to_download, len(data_split))):
    item = data_split[i]
    
    # Ambil byte PDF dari dataset
    pdf_bytes = item["pdf_bytes"]
    
    # Tentukan nama file (menggunakan kolom id/name jika ada, atau indeks loop)
    file_name = f"resume_{i+1}.pdf"
    file_path = os.path.join(output_dir, file_name)
    
    # Tulis byte ke file PDF
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)
        
    print(f"Berhasil menyimpan: {file_path}")

print("Selesai!")