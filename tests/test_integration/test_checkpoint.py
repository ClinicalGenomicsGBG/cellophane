from cellophane.testing import BaseTest, Invocation, literal


class Test_checkpoints(BaseTest):
    args = ["--workdir out", "--samples_file samples.yaml", "--tag DUMMY"]
    structure = {
        "modules/a.py": """
            from cellophane import runner, output, Output

            @output("out_a.txt", checkpoint="a")
            @output("out_b*.txt", checkpoint="b")
            @output("out_c_{sample.id}.txt", checkpoint="c")
            @output("out_e", checkpoint="e")
            @runner()
            def runner_(samples, checkpoints, config, workdir, logger, **_):
                a_1, hash_a_1 = checkpoints.a.check(), checkpoints.a.hexdigest()
                (workdir / "out_a.txt").touch()
                checkpoints.a.store()
                a_2, hash_a_2 = checkpoints.a.check(), checkpoints.a.hexdigest()

                (workdir / "out_b1.txt").touch()
                checkpoints["b"].store()
                b_1, hash_b_1 = checkpoints["b"].check(), checkpoints["b"].hexdigest()
                (workdir / "out_b2.txt").touch()
                b_2, hash_b_2 = checkpoints["b"].check(), checkpoints["b"].hexdigest()
                (workdir / "out_b2.txt").write_text("UPDATED")
                b_3, hash_b_3 = checkpoints["b"].check(), checkpoints["b"].hexdigest()

                c_1, hash_c_1 = checkpoints.c.check(), checkpoints.c.hexdigest()
                (workdir / f"out_c_{samples[0].id}.txt").touch()
                checkpoints.c.store()
                c_2, hash_c_2 = checkpoints.c.check(), checkpoints.c.hexdigest()
                checkpoints.c.store()

                d_1, hash_d_1 = checkpoints.d.check(), checkpoints.d.hexdigest()
                (workdir / "out_d.txt").write_text("DUMMY_D")
                d_2, hash_d_2 = checkpoints.d.check(), checkpoints.d.hexdigest()
                samples.output.add(Output(src="out_d.txt", dst="out_d.txt", checkpoint="d"))
                d_3, hash_d_3 = checkpoints.d.check(), checkpoints.d.hexdigest()

                e_1, hash_e_1 = checkpoints.e.check(), checkpoints.e.hexdigest()
                (workdir / "out_e").mkdir()
                checkpoints.e.store()
                e_2, hash_e_2 = checkpoints.e.check(), checkpoints.e.hexdigest()
                for i in range(500):
                    (workdir / f"out_e/{i}.txt").write_text(f"DUMMY FILE {i}")
                (workdir / "out_e" / "subdir").mkdir()
                for i in range(500):
                    (workdir / f"out_e/subdir/{i}.txt").write_text(f"DUMMY FILE {i}")
                e_3, hash_e_3 = checkpoints.e.check(), checkpoints.e.hexdigest()
                checkpoints.e.store()
                e_4, hash_e_4 = checkpoints.e.check(), checkpoints.e.hexdigest()


                a_3, hash_a_3 = checkpoints.a.check(), checkpoints.a.hexdigest()

                logger.info(f"{a_1=} (False)")
                logger.info(f"{a_2=} (True)")
                logger.info(f"{hash_a_1==hash_a_2=} (False)")
                logger.info(f"{hash_a_2==hash_a_3=} (True)")

                logger.debug(f"{hash_a_1=}")
                logger.debug(f"{hash_a_2=}")
                logger.debug(f"{hash_a_3=}")

                logger.info(f"{b_1=} (True)")
                logger.info(f"{b_2=} (False)")
                logger.info(f"{b_3=} (False)")
                logger.info(f"{hash_b_1==hash_b_2=} (False)")
                logger.info(f"{hash_b_2==hash_b_3=} (False)")

                logger.debug(f"{hash_b_1=}")
                logger.debug(f"{hash_b_2=}")
                logger.debug(f"{hash_b_3=}")

                logger.info(f"{c_1=} (False)")
                logger.info(f"{c_2=} (True)")
                logger.info(f"{hash_c_1==hash_c_2=} (False)")

                logger.debug(f"{hash_c_1=}")
                logger.debug(f"{hash_c_2=}")

                logger.info(f"{d_1=} (False)")
                logger.info(f"{d_2=} (False)")
                logger.info(f"{d_3=} (False)")
                logger.info(f"{hash_d_1==hash_d_2=} (True)")
                logger.info(f"{hash_d_2==hash_d_3=} (False)")

                logger.debug(f"{hash_d_1=}")
                logger.debug(f"{hash_d_2=}")
                logger.debug(f"{hash_d_3=}")

                logger.info(f"{e_1=} (False)")
                logger.info(f"{e_2=} (True)")
                logger.info(f"{e_3=} (False)")
                logger.info(f"{e_4=} (True)")

                logger.debug(f"{hash_e_1=}")
                logger.debug(f"{hash_e_2=}")
                logger.debug(f"{hash_e_3=}")
                logger.debug(f"{hash_e_4=}")
            """,
        "samples.yaml": """
            - id: a
              files:
              - input/a.txt
            - id: b
              files:
              - input/b.txt
            - id: c
              files:
              - input/c.txt
            - id: d
              files:
              - input/d.txt
        """,
        "input": {
            "a.txt": "INPUT_A",
            "b.txt": "INPUT_B",
            "c.txt": "INPUT_C",
            "d.txt": "INPUT_D",
        },
    }

    def test_checkpoints(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "a_1=False (False)",
            "a_2=True (True)",
            "hash_a_1==hash_a_2=False (False)",
            "hash_a_2==hash_a_3=True (True)",
            "b_1=True (True)",
            "b_2=False (False)",
            "b_3=False (False)",
            "hash_b_1==hash_b_2=False (False)",
            "hash_b_2==hash_b_3=False (False)",
            "c_1=False (False)",
            "c_2=True (True)",
            "hash_c_1==hash_c_2=False (False)",
            "d_1=False (False)",
            "d_2=False (False)",
            "d_3=False (False)",
            "hash_d_1==hash_d_2=True (True)",
            "hash_d_2==hash_d_3=False (False)",
            "e_1=False (False)",
            "e_2=True (True)",
            "e_3=False (False)",
            "e_4=True (True)",
        )
