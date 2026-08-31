import { createHash } from "node:crypto"

import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AuthBackdrop } from "../auth/AuthBackdrop"
import { DashboardBackdrop } from "../dashboard/DashboardBackdrop"
import { EventsBackdrop } from "../events/EventsBackdrop"
import { FooterBackdrop } from "../layout/FooterBackdrop"
import { NewsBackdrop } from "../news/NewsBackdrop"
import { ProfileBackdrop } from "../profile/ProfileBackdrop"
import { SettingsBackdrop } from "../settings/SettingsBackdrop"
import { ActivityBackdrop } from "../../features/activity/components/ActivityBackdrop"

const markupDigest = (markup: string) => createHash("sha256").update(markup).digest("hex")

describe("Presentational Backdrops Coverage Sweep", () => {
  it("renders AuthBackdrop under all branches", () => {
    const { rerender, container } = render(<AuthBackdrop />)
    const digests = [markupDigest(container.innerHTML)]

    rerender(<AuthBackdrop isNarrow={true} isMobile={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<AuthBackdrop isNarrow={false} isMobile={false} prefersReducedMotion={false} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<AuthBackdrop isNarrow={true} isMobile={false} prefersReducedMotion={false} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "846f53670834dcb65c78fd0d5a65a929549802d00f3d827f1c2cc21ff02f4622",
      "f0b25a79bb808a5fde9a8b8ec31eeeb0467828cdbea3269159f9ee9f9179c970",
      "846f53670834dcb65c78fd0d5a65a929549802d00f3d827f1c2cc21ff02f4622",
      "8e0d217bbd20352da43adabc68e3a71a39408375158f0568ca82ef9d0c4d9cd1",
    ])
  })

  it("renders DashboardBackdrop under all branches", () => {
    const { rerender, container } = render(
      <DashboardBackdrop isNarrow={false} prefersReducedMotion={false} />
    )
    const digests = [markupDigest(container.innerHTML)]

    rerender(<DashboardBackdrop isNarrow={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<DashboardBackdrop isNarrow={false} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "cdcd0bbefc86cee999cc058d03286d9e04d417416390e853a0e2a29f266a3357",
      "d56aac3e06d4fb16120d179b2fd1abf690c2b3126544d2f955ebb2ba03b1fab3",
      "cdcd0bbefc86cee999cc058d03286d9e04d417416390e853a0e2a29f266a3357",
    ])
  })

  it("renders EventsBackdrop under all branches", () => {
    const { rerender, container } = render(<EventsBackdrop />)
    const digests = [markupDigest(container.innerHTML)]

    rerender(<EventsBackdrop isNarrow={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<EventsBackdrop isNarrow={false} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<EventsBackdrop isNarrow={true} prefersReducedMotion={false} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "e3416f8e1b48b4a9808010dc07bd3eb47b072e2ec50586468062415868398aae",
      "d9fb91646abe549ec18b8819802d01d27b3600339ed865b58bcdbb9ee45ce3e5",
      "6d5e6aa01fe4618697593af7500d07c70dfdcbaf921a2ee44728f5ae051f6ee5",
      "8d337ee93a452d1aef7f831713c6782444fe33da5c0235c94038d6f6d09d05b0",
    ])
  })

  it("renders FooterBackdrop under all branches", () => {
    const { rerender, container } = render(<FooterBackdrop />)
    const digests = [markupDigest(container.innerHTML)]

    rerender(<FooterBackdrop isNarrow={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<FooterBackdrop isNarrow={false} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<FooterBackdrop isNarrow={true} prefersReducedMotion={false} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "b9c2f2b7d939d85b311caa85b0d1e8609533dead8132a912c5501a6889a9bba8",
      "f2256ef297d81ff945611eeffbeeae6bc64a2254cb50ded583d0166cad60b736",
      "8ebd9577fde38287d8272f83cc71491a7473fd9fa2484c5677bca334cd2a3055",
      "166e7adc822ac0db4e5c932ba4d007c3cd0d5f1e1c7477016e6fcec9a6dd4326",
    ])
  })

  it("renders NewsBackdrop under all branches", () => {
    const { rerender, container } = render(<NewsBackdrop isNarrow={false} />)
    const digests = [markupDigest(container.innerHTML)]

    rerender(<NewsBackdrop isNarrow={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<NewsBackdrop isNarrow={false} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<NewsBackdrop isNarrow={true} prefersReducedMotion={false} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "91abdc89ccb2953b59a2a2b1c060fdc5a26089c9c88f74e2ca23a4176da69f75",
      "0906492bc405a98d6e92a259c1f0935cf1c344e505436bdbe0606628d0b7811c",
      "a59deb0c785aad4185a6ebb914db618fffb9f5edd492d631fe8a42abccc9ed7e",
      "86fec22ec5648c68a6386c98efad51eac16890aa52537aea76966edc586ac840",
    ])
  })

  it("renders ProfileBackdrop under all branches", () => {
    const { rerender, container } = render(<ProfileBackdrop />)
    const digests = [markupDigest(container.innerHTML)]

    rerender(<ProfileBackdrop isNarrow={true} isMobile={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<ProfileBackdrop isNarrow={false} isMobile={false} prefersReducedMotion={false} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "8fc0c7fa53fb44d98ed55ae0de1a6aa164357028b575da9b8b47177b4d534cec",
      "cce915d1562de3ec79fb472356b7a815fb732416a6e9066e9a404b983cf0d9e9",
      "8fc0c7fa53fb44d98ed55ae0de1a6aa164357028b575da9b8b47177b4d534cec",
    ])
  })

  it("renders SettingsBackdrop under all branches", () => {
    const { rerender, container } = render(<SettingsBackdrop />)
    const digests = [markupDigest(container.innerHTML)]

    rerender(<SettingsBackdrop isNarrow={true} isMobile={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<SettingsBackdrop isNarrow={false} isMobile={false} prefersReducedMotion={false} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "75d630bdcd2e86ea182c6aa065d28bf29060df32c12e4e6cfa7fc66333a3ac16",
      "1f03ca87a073cd9a1b984ece2a74afe9393e4944c135bb6fd7592b904bc87ee4",
      "75d630bdcd2e86ea182c6aa065d28bf29060df32c12e4e6cfa7fc66333a3ac16",
    ])
  })

  it("renders ActivityBackdrop under all branches", () => {
    const { rerender, container } = render(
      <ActivityBackdrop isNarrow={false} prefersReducedMotion={false} />
    )
    const digests = [markupDigest(container.innerHTML)]

    rerender(<ActivityBackdrop isNarrow={true} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    rerender(<ActivityBackdrop isNarrow={false} prefersReducedMotion={true} />)
    digests.push(markupDigest(container.innerHTML))

    expect(digests).toEqual([
      "4d4f0bf42cae174655b18d6d7c121afa8b7c6f82d81cb8f860af46394204028b",
      "61f100d086103aab956435af034921fdd3c305f0a6c7cdca11c1bee2960c5db4",
      "903dd8a4eb7f4817e2845b8ff385d36b89b877d401004a3baa96ebc159113bd7",
    ])
  })
})
