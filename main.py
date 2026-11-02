import sys


def main() -> int:
    try:
        import customtkinter  
        import PIL  
    except ImportError as exc:
        print(f"Missing dependency: {exc.name}\nInstall everything with:  pip install -r requirements.txt")
        return 1
    from ui.app import HulagwayApp
    HulagwayApp().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
