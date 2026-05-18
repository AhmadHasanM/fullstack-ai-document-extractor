"use client";

export default function QueueStatus({
  queued,
  processing,
}: {
  queued: number;
  processing: number;
}) {
  return (
    <div className="bg-slate-800 p-4 rounded-2xl">
      <p>Queued: {queued}</p>
      <p>Processing: {processing}</p>
    </div>
  );
}