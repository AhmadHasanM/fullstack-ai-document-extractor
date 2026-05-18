"use client";

import Button from "../ui/Button";

export default function UploadButton({
  onClick,
  loading,
}: {
  onClick: () => void;
  loading?: boolean;
}) {
  return (
    <Button onClick={onClick} loading={loading}>
      Upload PDF
    </Button>
  );
}