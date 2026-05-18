export default function Card({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="bg-slate-800 rounded-2xl p-5 shadow">
      {children}
    </div>
  );
}