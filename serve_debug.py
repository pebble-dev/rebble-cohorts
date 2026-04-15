from cohorts import app


def main():
    app.run("0.0.0.0", 5000, debug=True)


if __name__ == "__main__":
    main()
