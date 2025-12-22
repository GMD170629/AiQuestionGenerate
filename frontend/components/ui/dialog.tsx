"use client"

import * as React from "react"
import {
  Dialog as MuiDialog,
  DialogProps as MuiDialogProps,
  DialogTitle,
  DialogContent as MuiDialogContent,
  DialogActions,
  IconButton,
} from '@mui/material'
import { Close } from '@mui/icons-material'
import { cn } from "@/lib/utils"

export interface DialogProps extends MuiDialogProps {
  open: boolean
  onOpenChange?: (open: boolean) => void
}

const Dialog = ({ open, onOpenChange, ...props }: DialogProps) => {
  return (
    <MuiDialog
      open={open}
      onClose={() => onOpenChange?.(false)}
      {...props}
    />
  )
}
Dialog.displayName = "Dialog"

const DialogContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => {
    return (
      <MuiDialogContent ref={ref} className={cn(className)} {...props}>
        {children}
      </MuiDialogContent>
    )
  }
)
DialogContent.displayName = "DialogContent"

const DialogHeader = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <DialogTitle className={cn("flex items-center justify-between", className)} {...props}>
    {children}
  </DialogTitle>
)
DialogHeader.displayName = "DialogHeader"

const DialogFooter = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <DialogActions className={cn(className)} {...props}>
    {children}
  </DialogActions>
)
DialogFooter.displayName = "DialogFooter"

const DialogTitleComponent = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, children, ...props }, ref) => (
  <DialogTitle ref={ref} className={cn(className)} {...props}>
    {children}
  </DialogTitle>
))
DialogTitleComponent.displayName = "DialogTitle"

const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-gray-500 dark:text-gray-400", className)}
    {...props}
  />
))
DialogDescription.displayName = "DialogDescription"

const DialogTrigger = ({ children, ...props }: any) => {
  return <>{children}</>
}
DialogTrigger.displayName = "DialogTrigger"

const DialogClose = ({ children, ...props }: any) => {
  return <>{children}</>
}
DialogClose.displayName = "DialogClose"

const DialogPortal = ({ children, ...props }: any) => {
  return <>{children}</>
}
DialogPortal.displayName = "DialogPortal"

const DialogOverlay = () => null
DialogOverlay.displayName = "DialogOverlay"

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogClose,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitleComponent as DialogTitle,
  DialogDescription,
}
