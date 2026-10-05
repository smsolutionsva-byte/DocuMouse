import { ReviewScreen } from "@/components/review/ReviewScreen";

export const metadata = { title: "Review" };

export default async function ReviewPage(props: PageProps<"/documents/[id]">) {
  const { id } = await props.params;
  return <ReviewScreen id={id} />;
}
