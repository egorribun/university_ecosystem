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

const expectedDigest = (...chunks: readonly string[]) => chunks.join("").replaceAll("_", "")

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
      expectedDigest(
        "846f_5367_0834",
        "dcb6_5c78_fd0d",
        "5a65_a929_5498",
        "02d0_0f3d_827f",
        "1c2c_c21f_f02f",
        "4622"
      ),
      expectedDigest(
        "f0b2_5a79_bb80",
        "8a5f_de9a_8b8e",
        "c31e_eeb0_4678",
        "28cd_bea3_2691",
        "59f9_ee9f_9179",
        "c970"
      ),
      expectedDigest(
        "846f_5367_0834",
        "dcb6_5c78_fd0d",
        "5a65_a929_5498",
        "02d0_0f3d_827f",
        "1c2c_c21f_f02f",
        "4622"
      ),
      expectedDigest(
        "8e0d_217b_bd20",
        "352d_a43a_dabc",
        "68e3_a71a_3940",
        "8375_158f_0568",
        "ca82_ef9d_0c4d",
        "9cd1"
      ),
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
      expectedDigest(
        "cdcd_0bbe_fc86",
        "cee9_99cc_058d",
        "0328_6d9e_04d4",
        "1741_6390_e853",
        "a0e2_a29f_266a",
        "3357"
      ),
      expectedDigest(
        "d56a_ac3e_06d4",
        "fb16_120d_179b",
        "2fd1_abf6_90c2",
        "b312_6544_d2f9",
        "55eb_b2ba_03b1",
        "fab3"
      ),
      expectedDigest(
        "cdcd_0bbe_fc86",
        "cee9_99cc_058d",
        "0328_6d9e_04d4",
        "1741_6390_e853",
        "a0e2_a29f_266a",
        "3357"
      ),
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
      expectedDigest(
        "e341_6f8e_1b48",
        "b4a9_8080_10dc",
        "07bd_3eb4_7b07",
        "2e2e_c505_8646",
        "8062_4158_6839",
        "8aae"
      ),
      expectedDigest(
        "d9fb_9164_6abe",
        "549e_c18b_8819",
        "802d_01d2_7b36",
        "0033_9ed8_65b5",
        "8bcd_bb9e_e45c",
        "e3e5"
      ),
      expectedDigest(
        "6d5e_6aa0_1fe4",
        "6186_9759_3af7",
        "500d_07c7_0dfd",
        "cbaf_921a_2ee4",
        "4728_f5ae_051f",
        "6ee5"
      ),
      expectedDigest(
        "8d33_7ee9_3a45",
        "2d1a_ef7f_8317",
        "13c6_7824_44fe",
        "33da_5c02_35c9",
        "4038_d6f6_d09d",
        "05b0"
      ),
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
      expectedDigest(
        "b9c2_f2b7_d939",
        "d85b_311c_aa85",
        "b0d1_e860_9533",
        "dead_8132_a912",
        "c550_1a68_89a9",
        "bba8"
      ),
      expectedDigest(
        "f225_6ef2_97d8",
        "1ff9_4561_1eef",
        "fbee_ae6b_c64a",
        "2254_cb50_ded5",
        "83d0_166c_ad60",
        "b736"
      ),
      expectedDigest(
        "8ebd_9577_fde3",
        "8287_d827_2f83",
        "cc71_491a_7473",
        "fd9f_a248_4c56",
        "77bc_a334_cd2a",
        "3055"
      ),
      expectedDigest(
        "166e_7adc_822a",
        "c0db_4e5c_932b",
        "a4d0_07c3_cd0d",
        "5f1e_1c74_7701",
        "6e6f_cec9_a6dd",
        "4326"
      ),
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
      expectedDigest(
        "91ab_dc89_ccb2",
        "953b_59a2_a2b1",
        "c060_fdc5_a260",
        "89c9_c88f_74e2",
        "ca23_a417_6da6",
        "9f75"
      ),
      expectedDigest(
        "0906_492b_c405",
        "a98d_6e92_a259",
        "c1f0_935c_f1c3",
        "44e5_0543_6bdb",
        "e060_6628_d0b7",
        "811c"
      ),
      expectedDigest(
        "a59d_eb0c_785a",
        "ad41_85a6_ebb9",
        "14db_618f_ffb9",
        "f5ed_d492_d631",
        "fe8a_42ab_ccc9",
        "ed7e"
      ),
      expectedDigest(
        "86fe_c22e_c564",
        "8c68_a638_6c98",
        "efad_51ea_c168",
        "90aa_5253_7aea",
        "7696_6edc_586a",
        "c840"
      ),
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
      expectedDigest(
        "8fc0_c7fa_53fb",
        "44d9_8ed5_5ae0",
        "de1a_6aa1_6435",
        "7028_b575_da9b",
        "8b47_177b_4d53",
        "4cec"
      ),
      expectedDigest(
        "cce9_15d1_562d",
        "e3ec_79fb_4723",
        "56b7_a815_fb73",
        "2416_a6e9_066e",
        "9a40_4b98_3cf0",
        "d9e9"
      ),
      expectedDigest(
        "8fc0_c7fa_53fb",
        "44d9_8ed5_5ae0",
        "de1a_6aa1_6435",
        "7028_b575_da9b",
        "8b47_177b_4d53",
        "4cec"
      ),
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
      expectedDigest(
        "75d6_30bd_cd2e",
        "86ea_182c_6aa0",
        "65d2_8bf2_9060",
        "df32_c12e_4e6c",
        "fa7f_c663_33a3",
        "ac16"
      ),
      expectedDigest(
        "1f03_ca87_a073",
        "cd9a_1b98_4ece",
        "2a74_afe9_393e",
        "4944_c135_bb6f",
        "d759_2b90_4bc8",
        "7ee4"
      ),
      expectedDigest(
        "75d6_30bd_cd2e",
        "86ea_182c_6aa0",
        "65d2_8bf2_9060",
        "df32_c12e_4e6c",
        "fa7f_c663_33a3",
        "ac16"
      ),
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
      expectedDigest(
        "4d4f_0bf4_2cae",
        "1746_55b1_8d6d",
        "7c12_1afa_8b7c",
        "6f82_d81c_b8f8",
        "60af_4639_4204",
        "028b"
      ),
      expectedDigest(
        "61f1_00d0_8610",
        "3aab_9564_35af",
        "0349_21fd_d3c3",
        "05f0_a6c7_cdca",
        "11c1_bee2_960c",
        "5db4"
      ),
      expectedDigest(
        "903d_d8a4_eb7f",
        "4817_e284_5b8f",
        "f385_d36b_89b8",
        "77d4_0100_4a3b",
        "aa96_ebc1_5911",
        "3bd7"
      ),
    ])
  })
})
