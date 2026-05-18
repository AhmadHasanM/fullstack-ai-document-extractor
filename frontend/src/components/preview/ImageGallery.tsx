export default function ImageGallery({
  images,
}: {
  images: string[];
}) {
  const API = process.env.NEXT_PUBLIC_API_URL;

  return (
    <div className="grid grid-cols-2 gap-4">
      {images.map((img) => (
        <img
          key={img}
          src={`${API}/${img}`}
          alt="preview"
          className="rounded-xl"
        />
      ))}
    </div>
  );
}