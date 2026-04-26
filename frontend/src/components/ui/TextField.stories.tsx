import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { TextField } from "./TextField"
import { Search, Mail, Lock } from "lucide-react"

const meta: Meta<typeof TextField> = {
  title: "UI/TextField",
  component: TextField,
  tags: ["autodocs"],
  argTypes: {
    label: { control: "text" },
    placeholder: { control: "text" },
    disabled: { control: "boolean" },
    error: { control: "boolean" },
    helperText: { control: "text" },
    fullWidth: { control: "boolean" },
    multiline: { control: "boolean" },
  },
}

export default meta
type Story = StoryObj<typeof TextField>

export const Default: Story = {
  args: {
    label: "Username",
    placeholder: "Enter username",
    value: "",
    onChange: () => {},
  },
}

export const WithIcons: Story = {
  args: {
    label: "Search",
    placeholder: "Search...",
    leadingIcon: <Search className="h-4 w-4" />,
    value: "",
    onChange: () => {},
  },
}

export const WithTrailingIcon: Story = {
  args: {
    label: "Email",
    placeholder: "Enter email",
    trailingIcon: <Mail className="h-4 w-4" />,
    value: "",
    onChange: () => {},
  },
}

export const ErrorState: Story = {
  args: {
    label: "Password",
    type: "password",
    value: "123",
    error: true,
    helperText: "Password is too weak",
    leadingIcon: <Lock className="h-4 w-4" />,
    onChange: () => {},
  },
}

export const Multiline: Story = {
  args: {
    label: "Bio",
    multiline: true,
    rows: 4,
    placeholder: "Tell us about yourself",
    value: "",
    onChange: () => {},
  },
}

export const CustomInputStyle: Story = {
  args: {
    label: "Custom Style",
    placeholder: "Dark background...",
    value: "",
    inputClassName: "bg-black/10 border-none",
    onChange: () => {},
  },
}
