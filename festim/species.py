from typing import List, Union
import ufl
from dolfinx import fem
import festim as F


class Species:
    """
    Hydrogen species class for H transport simulation.

    Args:
        name (str, optional): a name given to the species. Defaults to None.
        mobile (bool, optional): whether the species is mobile or not.

    Attributes:
        name (str): a name given to the species.
        mobile (bool): whether the species is mobile or not.
        solution (dolfinx.fem.Function): the solution for the current timestep
        prev_solution (dolfinx.fem.Function): the solution for the previous
            timestep
        test_function (ufl.Argument): the testfunction associated with this
            species
        sub_function_space (dolfinx.fem.function.FunctionSpaceBase): the
            subspace of the function space
        collapsed_function_space (dolfinx.fem.function.FunctionSpaceBase): the
            collapsed function space for a species in the function space. In
            case single species case, this is None.
        post_processing_solution (dolfinx.fem.Function): the solution for post
            processing
        concentration (dolfinx.fem.Function): the concentration of the species

    Usage:
        >>> from festim import Species, HTransportProblem
        >>> species = Species(name="H")
        >>> species.name
        'H'
        >>> my_model = HTransportProblem()
        >>> my_model.species.append(species)

    """

    def __init__(self, name: str = None, mobile=True) -> None:
        self.name = name
        self.mobile = mobile
        self.solution = None
        self.prev_solution = None
        self.test_function = None
        self.sub_function_space = None
        self.post_processing_solution = None
        self.collapsed_function_space = None

    def __repr__(self) -> str:
        return f"Species({self.name})"

    def __str__(self) -> str:
        return f"{self.name}"

    @property
    def concentration(self):
        return self.solution


class Trap(Species):
    """Trap species class for H transport simulation.

    This class only works for 1 mobile species and 1 trapping level and is
    for convenience, for more details see notes.

    Args:
        name (str, optional): a name given to the trap. Defaults to None.
        mobile_species (F.Species): the mobile species to be trapped
        k_0 (float): the trapping rate constant pre-exponential factor (m3 s-1)
        E_k (float): the trapping rate constant activation energy (eV)
        p_0 (float): the detrapping rate constant pre-exponential factor (s-1)
        E_p (float): the detrapping rate constant activation energy (eV)
        volume (F.VolumeSubdomain1D): The volume subdomain where the trap is.


    Attributes:
        name (str, optional): a name given to the trap. Defaults to None.
        mobile_species (F.Species): the mobile species to be trapped
        k_0 (float): the trapping rate constant pre-exponential factor (m3 s-1)
        E_k (float): the trapping rate constant activation energy (eV)
        p_0 (float): the detrapping rate constant pre-exponential factor (s-1)
        E_p (float): the detrapping rate constant activation energy (eV)
        volume (F.VolumeSubdomain1D): The volume subdomain where the trap is.
        trapped_concentration (F.Species): The immobile trapped concentration
        trap_reaction (F.Reaction): The reaction for trapping the mobile conc.
        empty_trap_sites (F.ImplicitSpecies): The implicit species for the empty trap sites

    Usage:
        >>> import festim as F
        >>> trap = F.Trap(name="Trap", species=H, k_0=1.0, E_k=0.2, p_0=0.1, E_p=0.3, volume=my_vol)
        >>> trap.name
        'Trap'
        >>> my_model = F.HydorgenTransportProblem()
        >>> my_model.traps = [trap]

    Notes:
        This convenience class replaces the need to specify an implicit species and
        the associated reaction, thus:

        cm = F.Species("mobile")
        my_trap = F.Trap(
            name="trapped",
            mobile_species=cm,
            k_0=1,
            E_k=1,
            p_0=1,
            E_p=1,
            n=1,
            volume=my_vol,
        )
        my_model.species = [cm]
        my_model.traps = [my_trap]

        is equivalent to:

        cm = F.Species("mobile")
        ct = F.Species("trapped")
        trap_sites = F.ImplicitSpecies(n=1, others=[ct])
        trap_reaction = F.Reaction(
            reactant=[cm, trap_sites],
            product=ct,
            k_0=1,
            E_k=1,
            p_0=1,
            E_p=1,
            volume=my_vol,
        )
        my_model.species = [cm, ct]
        my_model.reactions = [trap_reaction]


    """

    def __init__(
        self, name: str, mobile_species, k_0, E_k, p_0, E_p, n, volume
    ) -> None:
        super().__init__(name)
        self.mobile_species = mobile_species
        self.k_0 = k_0
        self.E_k = E_k
        self.p_0 = p_0
        self.E_p = E_p
        self.n = n
        self.volume = volume

        self.trapped_concentration = None
        self.reaction = None

    def create_species_and_reaction(self):
        """create the immobile trapped species object and the reaction for trapping"""
        self.trapped_concentration = F.Species(name=self.name, mobile=False)
        self.empty_trap_sites = F.ImplicitSpecies(
            n=self.n, others=[self.trapped_concentration]
        )

        self.reaction = F.Reaction(
            reactant=[self.mobile_species, self.empty_trap_sites],
            product=self.trapped_concentration,
            k_0=self.k_0,
            E_k=self.E_k,
            p_0=self.p_0,
            E_p=self.E_p,
            volume=self.volume,
        )


class ImplicitSpecies:
    """Implicit species class for H transport simulation.
    c = n - others

    Args:
        n (Union[float, callable]): the total concentration of the species
        others (List[Species]): the list of species from which the implicit
            species concentration is computed (c = n - others)
        name (str, optional): a name given to the species. Defaults to None.

    Attributes:
        name (str): a name given to the species.
        n (float): the total concentration of the species
        others (List[Species]): the list of species from which the implicit
            species concentration is computed (c = n - others)
        concentration (form): the concentration of the species
        value_fenics (): the total concentration as a fenics object
    """

    def __init__(
        self,
        n: Union[float, callable],
        others: List[Species] = None,
        name: str = None,
    ) -> None:
        self.name = name
        self.n = n
        self.others = others

    def __repr__(self) -> str:
        return f"ImplicitSpecies({self.name}, {self.n}, {self.others})"

    def __str__(self) -> str:
        return f"{self.name}"

    @property
    def concentration(self):
        if len(self.others) > 0:
            for other in self.others:
                if other.solution is None:
                    raise ValueError(
                        f"Cannot compute concentration of {self.name} because {other.name} has no solution"
                    )
        return self.value_fenics - sum([other.solution for other in self.others])

    def create_value_fenics(self, mesh, t: fem.Constant):
        """Creates the value of the density as a fenics object and sets it to
        self.value_fenics.
        If the value is a constant, it is converted to a fenics.Constant.
        If the value is a function of t, it is converted to a fenics.Constant.
        Otherwise, it is converted to a ufl Expression

        Args:
            mesh (dolfinx.mesh.Mesh) : the mesh
            t (dolfinx.fem.Constant): the time
        """
        x = ufl.SpatialCoordinate(mesh)

        if isinstance(self.n, (int, float)):
            self.value_fenics = F.as_fenics_constant(mesh=mesh, value=self.n)

        elif isinstance(self.n, (fem.Function, ufl.core.expr.Expr)):
            self.value_fenics = self.n

        elif callable(self.n):
            arguments = self.n.__code__.co_varnames

            if "t" in arguments and "x" not in arguments and "T" not in arguments:
                # only t is an argument
                if not isinstance(self.n(t=float(t)), (float, int)):
                    raise ValueError(
                        f"self.value should return a float or an int, not {type(self.n(t=float(t)))} "
                    )
                self.value_fenics = F.as_fenics_constant(
                    mesh=mesh, value=self.n(t=float(t))
                )
            else:
                kwargs = {}
                if "t" in arguments:
                    kwargs["t"] = t
                if "x" in arguments:
                    kwargs["x"] = x

                self.value_fenics = self.n(**kwargs)

    def update_density(self, t):
        """Updates the density value (only if the density is a function of time only)

        Args:
            t (float): the time
        """
        if callable(self.n):
            arguments = self.n.__code__.co_varnames
            if isinstance(self.value_fenics, fem.Constant) and "t" in arguments:
                self.value_fenics.value = self.n(t=t)


def find_species_from_name(name: str, species: list):
    """Returns the correct species object from a list of species
    based on a string

    Args:
        name (str): the name of the species
        species (list): the list of species

    Returns:
        species (festim.Species): the species object with the correct name

    Raises:
        ValueError: if the species name is not found in the list of species

    """
    for spe in species:
        if spe.name == name:
            return spe
    raise ValueError(f"Species {name} not found in list of species")
