import { Library } from "@/components/documents/Library";

export const metadata = { title: "Documents" };

export default async function DocumentsPage(props: PageProps<"/documents">) {
  const params = await props.searchParams;
  const status = typeof params.status === "string" ? params.status : undefined;
  return <Library initialStatus={status} />;
}
