import math
from mathutils import Vector
from .roof import Roof
from item.facade import Facade
from item.roof_profile import RoofProfile as ItemRoofProfile
from .geometry.trapezoid import TrapezoidRV, TrapezoidChainedRV
from .geometry.rectangle import RectangleFRA
from util import zero, zAxis


# Use https://raw.githubusercontent.com/wiki/vvoovv/blender-osm/assets/roof_profiles.blend
# to generate values for a specific profile
roofDataGabled = (
    (
        (0., 0.),
        (0.5, 1.),
        (1., 0.)
    ),
    {
        "numSamples": 10,
        "angleToHeight": 0.5
    }
)

roofDataRound = (
    (
        (0., 0.),
        (0.01, 0.195),
        (0.038, 0.383),
        (0.084, 0.556),
        (0.146, 0.707),
        (0.222, 0.831),
        (0.309, 0.924),
        (0.402, 0.981),
        (0.5, 1.),
        (0.598, 0.981),
        (0.691, 0.924),
        (0.778, 0.831),
        (0.854, 0.707),
        (0.916, 0.556),
        (0.962, 0.383),
        (0.99, 0.195),
        (1., 0.)
    ),
    {
        "numSamples": 1000,
        "angleToHeight": None
    }
)

roofDataGambrel = (
    (
        (0., 0.),
        (0.2, 0.6),
        (0.5, 1.),
        (0.8, 0.6),
        (1., 0.)
    ),
    {
        "numSamples": 10,
        "angleToHeight": None
    }
)

roofDataSaltbox = (
    (
        (0., 0.),
        (0.35, 1.),
        (0.65, 1.),
        (1., 0.)
    ),
    {
        "numSamples": 100,
        "angleToHeight": 0.35
    }
)


class ProfiledVert:
    """
    A class represents a vertex belonging to RoofProfile.polygon projected on the profile
    """
    def __init__(self, footprint, roof, vector, i):
        """
        Args:
            footprint (item.footprint.Footprint): a <Footprint> item
            roof (RoofProfile): an instance of the class <RoofProfile>
            vector (building.BldgVector): a vector that originates from the given polygon vertex to
                the next polygon vertex
            i (int): index (between 0 and <footprint.polygon.n-1>) of the polygon vertex
        """
        self.vector = vector
        self.i = i
        # the related index (in <verts>) of the polygon vertex in the basement of the volume
        vertBasementIndex = roof.vertOffset + i
        verts = footprint.building.renderInfo.verts
        proj = footprint.projections
        p = roof.profile
        d = footprint.direction
        v = verts[vertBasementIndex]
        # is the polygon vertex <i> located on a profile slot?
        onSlot = False
        createVert = True
        # X-coordinate in the profile coordinate system (i.e. along the roof direction);
        # the roof direction is calculated in roof.processDirection(..);
        # the coordinate can possess the value between 0. and 1.
        x = (proj[i] - proj[footprint.minProjIndex]) / footprint.polygonWidth
        # Y-coordinate in the profile coordinate system;
        # it's a coordinate (with an offset) across roof profile.
        # Note, that a perpendicular to <footprint.direction> is equal to <Vector((-d[1], d[0], 0.))
        self.y = -v[0]*d[1] + v[1]*d[0]
        # index in <roof.profileQ>
        index = roof.profileQ[
            math.floor(x * roof.numSamples)
        ]
        distance = x - p[index][0]
        
        if distance < zero:
            # the vertex <i> is located on the profile slot <roof.slots[index]>
            onSlot = True
            if roof.lEndZero and footprint.noWalls and not index:
                # The vertex <i> is located on the first profile slot <roof.slots[0]>,
                # also the building doesn't have walls and the profile value is equal to zero.
                # Therefore, no need to create a vertex, just use the basement vertex with the index <vertBasementIndex>
                createVert = False
                x = 0.
                vertIndex = vertBasementIndex
            else:
                # <x> and <z> coordinates for the profile point with the <index>
                x, h = p[index]
        elif abs(p[index + 1][0] - x) < zero:
            # the vertex <i> is located on the profile slot <roof.slots[index+1]>
            onSlot = True
            # increase <index> by one
            index += 1
            if roof.rEndZero and footprint.noWalls and index == roof.lastProfileIndex:
                # The vertex <i> is located on the last profile slot <roof.slots[-1]>,
                # also the building doesn't have walls and the profile value is equal to zero.
                # Therefore, no need to create a vertex, just use the basement vertex with the index <vertBasementIndex>
                createVert = False
                x = 1.
                vertIndex = vertBasementIndex
            else:
                # <x> and <z> coordinates for the profile point with the <index>
                x, h = p[index]
        else:
            # Polygon vertex <i> has X-coordinate in the profile coordinate system,
            # located between the profile slots <roof.slots[index]> and <roof.slots[index+1]>
            # Z-coordinate for the profile point with the <index>
            h1 = p[index][1]
            # Z-coordinate for the profile point with the <index+1>
            h2 = p[index+1][1]
            # given <h1> and <h2>, calculate Z-coordinate for the polygon vertex <i>
            h = h1 + (h2 - h1) / (p[index+1][0] - p[index][0]) * distance
        if createVert:
            vertIndex = len(verts)
            # note, that <h> is multiplied by the roof height <footprint.roofHeight>
            verts.append(Vector((v.x, v.y, footprint.roofVerticalPosition + footprint.roofHeight * h)))
            self.h = h
        else:
            self.h = 0.
        # The meaning of <self.index> is that the polygon vertex <i> projected on the profile
        # has X-coordinate in the profile coordinate system,
        # located between the profile slots <roof.slots[index]> and <roof.slots[index+1]>
        self.index = index
        # If the polygon vertex <i> is located on a profile slot (i.e. <self.onSlot> is <True>) and
        # has <self.index>, it can be located only on the slot <roof.slots[index]>,
        # not (!) on the slot <roof.slots[index+1]>
        self.onSlot = onSlot
        # X-coordinate in the profile coordinate system, it can possess the value between 0. and 1.
        self.x = x
        # vertex index of the polygon vertex <i> projected on the profile
        self.vertIndex = vertIndex


class Slot:
    """
    An instance of the class is created for each profile point.
    The class is used to form faces for the profiled roof.
    
    See https://github.com/vvoovv/blender-osm/wiki/Profiled-roofs for description and illustration
    of concepts and algorithms used in the code. Specifically, the image <Main> from that webpage is
    used a number of times to illustrate the code.
    """
    
    def __init__(self, x, volumeGenerator):
        """
        Args:
            x (float): A location between 0. and 1. of the slot
                in the profile coordinate system
            volumeGenerator(RoofProfile): A volume generator
        """
        self.x = x
        self.volumeGenerator = volumeGenerator
        # Each element of <self.parts> is a Python tuple:
        # (y, part, reflection, index in <self.parts>)
        # A part is sequence of vertices that start at a slot and ends at the same slot or at a neighboring one.
        # Y-coordinate of the first vertex of the part in the coordinate system of the profile is
        # stored for each part.
        # Example of parts on the image <Main> for slots[2]:
        #     [16, 17]: starts at slots[2], ends at slots[3]
        #     [20, 2, 21]: starts at slots[2], ends at slots[2]
        #     [21, 3, 22]: starts at slots[2], ends at slots[2]
        #     [25, 26]: starts at slots[2], ends at slots[1]
        self.parts = []
        # <self.partsR> is used to store incomplete roof faces started in <self.trackUp(..)>
        # Each of those incomplete roof faces is completed in subsequent <self.trackDown(..)>
        self.partsR = []
        # <self.endAtSelf[index]> indicates if a <part> from <self.parts> with <part[3] == index>
        # ends at self (True) or at neighbor slot (False).
        # We use a separate Python list for <self.endAtSelf> to get some memory usage gain.
        # We could use <self.parts> to store that information, however in that case we would need
        # to use a Python list instead of Python tuple for each element of <self.parts>,
        # since the information where a part ends is set post factum, not during the creation of
        # an element of <self.parts>
        self.endAtSelf = []
    
    def reset(self):
        self.parts.clear()
        self.partsR.clear()
        self.endAtSelf.clear()
        # the current index in <self.parts>
        self.index = 0
    
    def prepare(self):
        """
        Prepare the slot to form roof faces.
        
        Specifically, sort <self.parts> by <y> coordinate in the profile coordinate system 
        """
        # remember that <y == part[0]>, where <part> is an element of <self.parts>
        self.parts.sort(key = lambda p: p[0])
    
    def append(self, vertIndex, y=None, originSlot=None, reflection=None):
        """
        Append <vertIndex> to the slot.
        
        If <y>, <originSlot> and <reflection> are given, create a new part starting with <vertIndex> and
        its <y> coordinate in the profile coordinate system.
        Otherwise append <vertIndex> to the last part of the slot (i.e. to <self.parts[-1]>)
        
        Args:
            vertIndex (int): Vertex index to append to the slot
            y (float): Y-coordinate in the profile coordinate system of the vertex with the index <vertIndex>
                where the new part starts
            originSlot (Slot): The last part of <originSlot> (i.e. <originSlot.parts[-1]>) ends at <self>.
                We need <originSlot> here to set <originSlot.endAtSelf> for the last part of <originSlot>.
                So after the execution of the method, <originSlot.endAtSelf[-1]> will correspond to
                <originSlot.parts[-1]>
            reflection (bool or None): Is there a reflection at <vertIndex>>
                <reflection> can have 3 values:
                <None>: no reflection
                <True>: reflection to the right (the example is give on the image <Main>; there is reflection
                    at the vertex <5> on the slot <slots[3]>)
                <False>: reflection to the left
        """
        parts = self.parts
        if y is None:
            # append <vertIndex> to the last part of the slot
            parts[-1][1].append(vertIndex)
        else:
            # create a new part starting with <vertIndex> and its <y> coordinate in the profile coordinate system
            parts.append((y, [vertIndex], reflection, self.index))
            # set <originSlot.endAtSelf> for the last part of <originSlot>
            originSlot.endAtSelf.append(originSlot is self)
            self.index += 1
    
    def trackDown(self, roofItem, slotIndex, index=None, destVertIndex=None):
        """
        Track the slot downwards to form roof faces.
        
        Args:
            roofItem (item.roof_profile.RoofProfile): A roof item.
            slotIndex (int): An index of <self.slots> we are building the roof sides for.
                No roof sides can be built for the very last slot.
            index (int or None): If <index> is not <None>, it indicates a part in <self.parts> where to begin,
                otherwise start from the very top of the slot.
            destVertIndex (int or None): If <index> is not <None>, <destVertIndex> indicates where to stop.
                There is no example on the image <Main>. However the idea is completely similar to
                the related example in <self.trackUp(..)>.
        """
        parts = self.parts
        # Incomplete roof faces for that slot are stored in <self.n.partsR>.
        # <indexPartR> specifies the index of the element in <self.n.partsR>
        # to complete the current part.
        indexPartR = -1
        # We start from the very top if <index> is <None>.
        # The example of that case on the image <Main> for <slots[1]>:
        # <len(part) == 4>
        # <index == 2>
        index = (len(parts) if index is None else index) - 2
        # <vertIndex0> is set to the first vertex index of the next part, i.e. to <parts[index+1][1][0]>
        vertIndex0 = None
        while index >= 0:
            # the current part
            _, part, reflection, _index = parts[index]
            if vertIndex0 is None:
                # set <vertIndex0> to the first vertex index of the next part
                vertIndex0 = parts[index+1][1][0]
                # start a new roof face
                roofFace = []
            # <False> for the reflection means reflection to the left
            if reflection is False:
                # No example for that case on the image <Main>. However the idea is completely similar to
                # the related example in <self.trackUp(..)>.
                index -= 1
                continue
            # extend <roofFace> with vertex indices from <part>
            roofFace.extend(part)
            if part[-1] == vertIndex0:
                # Сame up
                # The example of that case on the image <Main> for <slots[3]>:
                # <index == 0>
                # <part == [17, 13, 14, 18]>
                # <vertIndex0 == 18>
                # The roof face is completed
                self.volumeGenerator.addRoofSide(roofFace, roofItem, slotIndex)
                # Setting <vertIndex0> to <None> means that we start a new roof face in
                # the next iteration of the <while> cycle
                vertIndex0 = None
            elif not self.endAtSelf[_index]:
                # Came to the neighbor from the right.
                # The example of that case on the image <Main> for <slots[1]>:
                # <index == 0>
                # <part == [15, 16]>
                # <roofFace == [27, 9, 10, 28, 15, 16]>
                # <self.n == slots[2]>
                # <self.n.partsR == [[19, 0, 1, 20, 25, 26]]>
                # Complete <roofFace> with the incomplete roof face <self.n.partsR[indexPartR]>
                roofFace.extend(self.n.partsR[indexPartR])
                # Change <indexPartR> to use the next incomplete roof face of <self.n.partsR>
                # in the next iterations of the <while> cycle
                indexPartR -= 1
                # The roof face is complete
                self.volumeGenerator.addRoofSide(roofFace, roofItem, slotIndex)
                # Setting <vertIndex0> to <None> means that we start a new roof face in
                # the next iteration of the <while> cycle
                vertIndex0 = None
            elif part[-1] != parts[index-1][1][0]:
                # No example for that case on the image <Main>. However the idea is completely similar to
                # the related example in <self.trackUp(..)>.
                # Basically, that case means that there is an island between
                # the vertices <part[0]> and <part[-1]>
                # We need to process that island in line below
                index = self.trackDown(
                    roofItem,
                    slotIndex,
                    # The edge case:
                    # if there is a reflection to the right (i.e. <reflection is True>),
                    # correct the index given as the parameter to <self.trackDown(..)>
                    index+1 if reflection is True else index,
                    part[-1]
                )
                if reflection is True:
                    # The edge case:
                    # the reflection to the right (i.e. <reflection is True>) forms
                    # an island between the vertices <part[0]> and <part[-1]>.
                    # The island has been already visited during the call
                    # of <self.trackDown(..)> a few lines above.
                    # So we set <reflection> to <None>
                    reflection = None
            if not destVertIndex is None:
                if parts[index-1][1][0] == destVertIndex:
                    # No example for that case on the image <Main>. However the idea is completely similar to
                    # the related example in <self.trackUp(..)>.
                    return index
                elif reflection is True and part[0]==destVertIndex:
                    # The edge case:
                    # if there is a reflection to the right (i.e. <reflection is True>)
                    # and <part[0]==destVertIndex>, correct the returned index
                    return index+1
            # Proceed to the previous part downwards by decreasing <index>.
            # <True> for the reflection means reflection to the right
            # The example of case with <reflection is True> on the image <Main> for <slots[3]>:
            # <reflection is True>
            # <index == 3>
            # <part == [5, 6, 24]>
            # For that case in the next iteration of the <while> cycle
            # we proceed to <index == 2> and <part == [23, 4, 5]>,instead of <index == 1>,
            # where there is no part for tracking it downwards.
            index -= 1 if reflection is True else 2

    def trackUp(self, roofItem, slotIndex, index=None, destVertIndex=None):
        """
        Track the slot upwards to form roof faces.
        
        Args:
            roofItem (item.roof_profile.RoofProfile): A roof item.
            slotIndex (int): An index of <self.slots> we are building the roof sides for.
                No roof sides can be built for the very last slot.
            index (int or None): If <index> is not <None>, it indicates a part in <self.parts> where to begin,
                otherwise start from the very bottom of the slot.
            destVertIndex (int or None): If <index> is not <None>, <destVertIndex> indicates where to stop.
                See the example on the image <Main> for the slot <slots[2]>.
                <self.trackUp(..)> is called with <index == 1>, <destVertIndex == 20>.
                The example is elaborated further in the code below.
        """
        parts = self.parts
        numParts = len(parts)
        # Continue the example with the input attribute <index == 1>.
        # <index> will be set to <3> in the line below if <index == 1>.
        # Otherwise we start from the very bottom of the slots and set <index> to <1>
        index = 1 if index is None else index+2
        # <vertIndex0> is set to the first vertex index of the previous part, i.e. to <parts[index-1][1][0]>
        vertIndex0 = None
        while index < numParts:
            # the current part
            _, part, reflection, _index = parts[index]
            if vertIndex0 is None:
                # set <vertIndex0> to the first vertex index of the previous part
                vertIndex0 = parts[index-1][1][0]
                # start a new roof face
                roofFace = []
            # <True> for the reflection means reflection to the right
            if reflection is True:
                # The example of that case on the image <Main>:
                # there is reflection at the vertex <5> on the slot <slots[3]>
                # <index == 3>
                # We increase <index> by <1> in the line below; so we will come to the part [24, 25]
                # in the next iteration of the <while> cycle
                index += 1
                continue
            # extend <roofFace> with vertex indices from <part>
            roofFace.extend(part)
            if part[-1] == vertIndex0:
                # Сame down
                # The example of that case on the image <Main> for <slots[1]>:
                # <index == 1>
                # <part == [28, 11, 12, 15]>
                # <vertIndex0 == 15>
                # The roof face is complete
                self.volumeGenerator.addRoofSide(roofFace, roofItem, slotIndex)
                # Setting <vertIndex0> to <None> means that we start a new roof face in
                # the next iteration of the <while> cycle
                vertIndex0 = None
            elif not self.endAtSelf[_index]:
                # Came to the neighbor from the left.
                # The example of that case on the image <Main> for <slots[2]>:
                # <index == 5>
                # <part == [25, 26]>
                # <roofFace == [19, 0, 1, 20, 25, 26]>
                # Store the incomplete roof face <roofFace> in <self.partsR>. It will be completed in
                # the subsequent call of <self.trackDown(..)>
                self.partsR.append(roofFace)
                # Setting <vertIndex0> to <None> means that we start a new roof face in
                # the next iteration of the <while> cycle
                vertIndex0 = None
            elif part[-1] != parts[index+1][1][0]:
                # The example of that case on the image <Main> for <slots[2]>:
                # <index == 1>
                # <part == [19, 0, 1, 20]>
                # <part[-1] == 20>
                # <parts[index+1][1] == [22, 3, 21]>
                # <parts[index+1][1][0] == 22>
                # Basically, that case means that there is an island between the vertices <19> and <20>
                # We need to process that island in line below
                index = self.trackUp(roofItem, slotIndex, index, part[-1])
            if not destVertIndex is None and parts[index+1][1][0] == destVertIndex:
                # The example of that case on the image <Main> for <slots[2]>:
                # <destVertIndex == 20>
                # <index == 3>
                # <part == [21, 3, 22]>
                # <parts[index+1][1] == [20, 2, 21]>
                # <parts[index+1][1][0] == 20>
                return index
            # Proceed to the next part upwards by increasing <index>.
            # <False> for the reflection means reflection to the left
            index += 1 if reflection is False else 2
    
    def processWallFace(self, indices, pv1, pv2):
        """
        A child class may provide realization for this methods
        
        Args:
            indices (list): Vertex indices for the wall face
            pv1 (ProfiledVert): the first profiled vertex of the two between which the slot vertex is located
            pv2 (ProfiledVert): the second profiled vertex of the two between which the slot vertex is located
        """
        pass


class RoofProfile(Roof):
    
    # default roof height
    height = 1.
    
    def __init__(self, profileData, data, volumeAction, itemRenderers):        
        """
        Args:
            profileData (tuple): profile values and some attributes to define a profiled roof,
                e.g. gabledRoof, roundRoof, gambrelRoof, saltboxRoof
        """
        super().__init__("RoofProfile", data, volumeAction, itemRenderers)
        self.hasGable = True
        # geometries for wall faces
        self.geometryRectangle = RectangleFRA()
        self.geometryTrapezoid = TrapezoidRV()
        self.geometryTrapezoidChained = TrapezoidChainedRV()
        
        self.hasRidge = True
        
        # actual profile values as a Python tuple of (x, y)
        profile = profileData[0]
        self.profile = profile
        numProfilesPoints = len(profile)
        self.numSlots = numProfilesPoints
        self.lastProfileIndex = numProfilesPoints - 1
        # create profile slots
        slots = tuple(Slot(profile[i][0], self) for i in range(numProfilesPoints) )
        # set the next slot, it will be need in further calculations
        for i in range(self.lastProfileIndex):
            slots[i].n = slots[i+1]
        self.slots = slots
        
        for attr in profileData[1]:
            setattr(self, attr, profileData[1][attr])
        
        # is the y-coordinate at <x=0.0> (the left end of the profile) is equal to zero?
        self.lEndZero = not profile[0][1]
        # is the y-coordinate at <x=1.0> (the right end of the profile) is equal to zero?
        self.rEndZero = not profile[-1][1]
        
        # Quantize <profile> with <numSamples> to get performance gain
        # Quantization is needed to perform the following action very fast.
        # Given x-coordinate <x> between 0. and 1. in the profile coordinate system,
        # find two neighboring slots between which <x> is located
        _profile = tuple(math.ceil(p[0]*self.numSamples) for p in profile)
        profileQ = []
        index = 0
        for i in range(self.numSamples):
            if i >= _profile[index+1]:
                index += 1  
            profileQ.append(index)
        profileQ.append(index)
        self.profileQ = profileQ
        
        # where the vertices for the volume start in <footprint.building.renderInfo.verts>
        self.vertOffset = 0
        
        self._initUv()
    
    def _initUv(self):
        """
        Extra initialization code related to the stuff needed for UV-mapping
        """
        slots = self.slots
        p = self.profile
        
        # The key in the following Python dictionary is an vertex index in <building.footprint>;
        # the value is a Python tuple with the elements described in code of the method
        # item_renderer/texture/roof_profile/RoofProfile/getUvs(..)
        self.roofVertexData = {}
        
        self.dx_2 = tuple(
            (slots[i+1].x-slots[i].x)*(slots[i+1].x-slots[i].x)
            for i in range(self.lastProfileIndex)
        )
        self.dy_2 = tuple(
            (p[i+1][1]-p[i][1])*(p[i+1][1]-p[i][1])
            for i in range(self.lastProfileIndex)
        )
        # An element of <self.slopes> can take 3 possible value:
        # True (positive slope of a profile part)
        # False (negative slope of a profile part)
        # None (flat profile part)
        self.slopes = tuple(
            True if p[i+1][1]>p[i][1] else
            (False if p[i+1][1]<p[i][1] else None)
            for i in range(self.lastProfileIndex)
        )
        # the lenths of profile parts
        self.partLength = [0. for i in range(self.lastProfileIndex)]
    
    def init(self, footprint):
        roofItem = super().init(footprint)
        
        if not footprint.valid:
            return
        
        self.initProfile()
        
        if not footprint.projections:
            self.processDirection(footprint)
        
        self.initUv(footprint)
        
        return roofItem

    def validate(self, footprint):
        """
        Additional validation
        """
        return
    
    def initUv(self, footprint):
        """
        Initialize the stuff related to UV-mapping
        """
        slots = self.slots
        
        self.roofVertexData.clear()
        # minimum and maximum Y-coordinates in the profile coordinate system
        # for the roof vertices
        self.minY = math.inf
        self.maxY = -math.inf
        
        self.polygonWidth_2 = footprint.polygonWidth * footprint.polygonWidth
        self.roofHeight_2 = footprint.roofHeight * footprint.roofHeight
        for i in range(self.lastProfileIndex):
            self.partLength[i] = footprint.polygonWidth * (slots[i+1].x-slots[i].x)\
                if self.slopes[i] is None else\
                math.sqrt(self.polygonWidth_2*self.dx_2[i] + self.roofHeight_2 * self.dy_2[i])
    
    def initProfile(self):
        # The last slot with the index <self.lastProfileIndex> isn't touched,
        # so no need to reset it
        for i in range(self.lastProfileIndex):
            self.slots[i].reset()
    
    def getRoofItem(self, footprint):
        return ItemRoofProfile(footprint)
    
    def render(self, footprint, roofItem):
        polygon = footprint.polygon
        verts = footprint.building.renderInfo.verts
        self.vertOffset = len(verts)
        # vertices for the basement of the volume
        minHeight = footprint.minHeight
        verts.extend(Vector( (v[0], v[1], minHeight) ) for v in polygon.verts)
        
        slots = self.slots
        
        # the current slot: start from the leftmost slot
        self.slot = slots[0]
        # the slot from which the last part in <slot.parts> originates
        self.originSlot = slots[0]
        
        # Start with the vertex from <polygon> with <x=0.> in the profile coordinate system;
        # the variable <i0> is needed to break the cycle below
        i = i0 = footprint.minProjIndex
        vector = footprint.minProjVector
        # Create a profiled vertex out of the related basement vertex;
        # <pv> stands for profiled vertex
        pv1 = pv0 = self.getProfiledVert(footprint, vector, i)
        _pv = None
        while True:
            i = polygon.next(i)
            if i == i0:
                # came to the starting vertex, so break the cycle
                break
            vector = vector.next
            # create a profiled vertex out of the related basement vertex
            pv2 = self.getProfiledVert(footprint, vector, i)
            # The order of profiled vertices is <_pv>, <pv1>, <pv2>
            # Create in-between vertices located on the slots for the segment between <pv1> and <pv2>),
            # also form a wall face under the segment between <pv1> and <pv2>
            self.createProfileVertices(pv1, pv2, _pv, footprint)
            _pv = pv1     
            pv1 = pv2
        # Create in-between vertices located on the slots for the closing segment between <pv1> and <pv0>,
        # also form a wall face under the segment between <pv1> and <pv0>
        self.createProfileVertices(pv1, pv0, _pv, footprint)
        
        # Append the vertices from the first part of the <slot[0]> (i.e. slots[0].parts[0])
        # to the last part of <slots[1]> (i.e. slots[1].parts[-1])
        # Example on the image <Main>:
        # slots[0].parts[0][1] is [11, 12, 15]
        # slots[1].parts[-1][1] is [28, 11]
        # after the execution of the line of below:
        # slots[1].parts[-1][1] is [28, 11, 12, 15]
        slots[1].parts[-1][1].extend(slots[0].parts[0][1][i] for i in range(1, len(slots[0].parts[0][1])))
        # the last part of <slots[1]> ends at self
        slots[1].endAtSelf.append(True)
        
        # Prepare the slots to form roof faces;
        # note that slots[0] and slots[-1] aren't used in the calculations
        for i in range(1, self.lastProfileIndex):
            slots[i].prepare()
        
        # Below is the cycle to form roof faces
        # Each time a band between the neighboring slots
        # <slotL> (a slot from the left) and <slotR> (a slot from the right) is considered.
        # We track <slotR> upwards by executing <slotR.trackUp(..)>,
        # then we track <slotL> downwards by executing slotL.trackDown(..)
        slotR = slots[1]
        slotR.trackUp(roofItem, 0)
        self.onRoofForSlotCompleted(0)
        for slotIndex in range(1, self.lastProfileIndex):
            slotL = slotR
            slotR = slots[slotIndex+1]
            slotR.trackUp(roofItem, slotIndex)
            slotL.trackDown(roofItem, slotIndex)
            self.onRoofForSlotCompleted(slotIndex)
        
        self.facadeRenderer.render(footprint)
        self.roofRenderer.render(roofItem)
    
    def getProfiledVert(self, footprint, vector, i):
        """
        A factory method to get an instance of the <ProfiledVert> class.
        
        The arguments of the method are the same as for the constructor
        of the <ProfiledVert> class.
        """
        pv = ProfiledVert(footprint, self, vector, i)
        
        # the code below is needed for UV-mapping
        y = pv.y
        # The elements of the Python tuple below are described in code of the method
        # item_renderer/texture/roof_profile/RoofProfile/getUvs(..)
        self.roofVertexData[pv.vertIndex] = (
            pv.onSlot,
            pv.index if pv.onSlot else self.getTexCoordAlongProfile(pv, footprint),
            y
        )
        # update <self.minY> and <self.maxY> if necessary
        if y < self.minY:
            self.minY = y
        elif y > self.maxY:
            self.maxY = y
        return pv

    def getTexCoordAlongProfile(self, pv, footprint):
        slots = self.slots
        p = self.profile
        slope = self.slopes[pv.index]
        if slope:
            dx = pv.x - slots[pv.index].x
            dh = pv.h - p[pv.index][1]
            texCoord = math.sqrt(self.polygonWidth_2*dx*dx + self.roofHeight_2*dh*dh)
        elif slope is False:
            dx = slots[pv.index+1].x - pv.x
            dh = pv.h - p[pv.index+1][1]
            texCoord = math.sqrt(self.polygonWidth_2*dx*dx + self.roofHeight_2*dh*dh)
        else: # slope is None
            texCoord = footprint.polygonWidth * (slots[pv.index+1].x - pv.x)
        return texCoord
    
    def createProfileVertices(self, pv1, pv2, _pv, footprint):
        """
        Create in-between vertices located on the slots for the segment between <pv1> and <pv2>,
        also form a wall face under the segment between <pv1> and <pv2>.
        
        For example (see the image <Main>), if <pv1> was created for the polygon vertex with the index <3>,
        <pv2> was created for the polygon vertex with the index <4>, then two vertices with the indices
        <22> and <23> will be created for the intersection of the segment between <pv1> and <pv2> with
        the slots <slots[2]> and <slots[3]> respectively.
         
        Args:
            pv1 (ProfiledVert): Defines the first vertex of the segment of <self.polygon> projected on the profile
            pv2 (ProfiledVert): Defines the second vertex of the segment of <self.polygon> projected on the profile
            _pv (ProfiledVert): Precedes <pv1>
        """
        verts = footprint.building.renderInfo.verts
        p = self.profile
        slots = self.slots
        # the current slot
        slot = self.slot
        
        # index of the slot for <pv1>
        index1 = pv1.index
        # index of the slot for <pv1>
        index2 = pv2.index
        
        # skip the polygon vertex with the index <self.vertOffset+pv1.i> from including it to the wall face?
        skip1 = footprint.noWalls and pv1.onSlot and\
            ((self.lEndZero and not index1) or\
            (self.rEndZero and index1 == self.lastProfileIndex))
        # skip the polygon vertex with the index <self.vertOffset+pv2.i> from including it to the wall face?
        skip2 = footprint.noWalls and pv2.onSlot and\
            ((self.lEndZero and not index2) or\
            (self.rEndZero and index2 == self.lastProfileIndex))

        if skip1 and skip2 and index1 == index2:
            # In the case the building doesn't have walls and both <pv1> and <pv2>
            # are located either on <slots[0]> or <slots[-1]>
            if _pv is None:
                # We are at <slots[0]> and just started, so create the very first part for the <slot>;
                # <slot> is <slots[0]>
                slot.append(pv1.vertIndex, pv1.y, self.originSlot)
            # append <pv2.vertIndex> to the last part of the <slot> (i.e. to <slot.parts[-1]>)
            slot.append(pv2.vertIndex)
            # we are done
            return
        # Start a wall face under the segment between <pv1> and <pv2>;
        # ensure that the first two vertices will be always
        # the lowest vertices located on the same height;
        # that's important for the correct uv-mapping
        if skip1:
            _wallIndices = [pv1.vertIndex]
            appendPv1 = False
        else:
            _wallIndices = [self.vertOffset + pv1.i]
            appendPv1 = True
        if not skip2:
            _wallIndices.append(self.vertOffset + pv2.i)
        _wallIndices.append(pv2.vertIndex)
        
        # basement vertices (i.e. polygon vertices)
        v1 = verts[self.vertOffset + pv1.i]
        v2 = verts[self.vertOffset + pv2.i]
        if not _pv is None:
            _v = verts[self.vertOffset + _pv.i]
        
        if _pv is None:
            # We are at <slots[0]> and just started, so create the very first part for the <slot>;
            # <slot> is <slots[0]>
            slot.append(pv1.vertIndex, pv1.y, self.originSlot)
        elif pv1.onSlot:
            # <pv1> is located on a profile slot
            
            # <reflection> can have 3 values:
            # <None>: no reflection
            # <True>: reflection to the right (see below an example)
            # <False>: reflection to the left
            reflection = None
            # If <appendToSlot> is <True> we change the current slot and create a new part for that slot.
            # If <appendToSlot> is <False> we continue with the <slot> and its last part <slot.parts[-1]>.
            appendToSlot = False
            if pv2.onSlot and index1 == index2:
                # <pv2> is located on the same profile slot as <pv1>
                # Example on the image <Main>:
                # <_pv> ~ <6>
                # <pv1> ~ <7>
                # <pv2> ~ <8>
                if (index1 != self.lastProfileIndex and _pv.x < pv1.x and pv1.y > pv2.y)\
                    or (index1 and _pv.x > pv1.x and pv1.y < pv2.y):
                    # The conditions <index1 != self.lastProfileIndex> and <index1>
                    # are to prevent erroneous behavior due to 180 degrees angle as the result of mapping error or
                    # precision error caused by the nature of <zero> variable
                    
                    # <6>, <7>, <8> on the image <Main> doesn't satisfy that condition
                    appendToSlot = True
            elif pv1.x < pv2.x:
                # going from the left to the right
                if _pv.x < pv1.x:
                    appendToSlot = True
                elif index1: # i.e. index1 != 0
                    # The condition <index1> is to prevent
                    # erroneous reflection due to 180 degrees angle as the result of mapping error or
                    # precision error caused by the nature of <zero> variable
                    if _pv.onSlot and _pv.index == pv1.index:
                        # <_pv> is located on the same profile slot as <pv1>
                        if _pv.y < pv1.y:
                            appendToSlot = True
                            # no reflection in this case!
                    elif (pv2.x-pv1.x)*(_pv.y-pv1.y) - (pv2.y-pv1.y)*(_pv.x-pv1.x) < 0.:
                        # <_pv.x > pv1.x> and <pv1.x < pv2.x>
                        appendToSlot = True
                        # <True> for the reflection means reflection to the right
                        reflection = True
                        # Example of a reflection to the right on the image <Main>:
                        # <_pv> ~ <4>
                        # <pv1> ~ <6>
                        # <pv2> ~ <6>
            else:
                # going from the right to the left
                if _pv.x > pv1.x:
                    appendToSlot = True
                elif index1 != self.lastProfileIndex:
                    # The condition <index1 != self.lastProfileIndex> is to prevent
                    # erroneous reflection due to 180 degrees angle as the result of mapping error or
                    # precision error caused by the nature of <zero> variable
                    if _pv.onSlot and _pv.index == pv1.index:
                        # <_pv> is located on the same profile slot as <pv1>
                        if _pv.y > pv1.y:
                            appendToSlot = True
                            # no reflection in this case!
                    elif (pv2.x-pv1.x)*(_pv.y-pv1.y) - (pv2.y-pv1.y)*(_pv.x-pv1.x) < 0.:
                        # <_pv.x < pv1.x> and <pv1.x > pv2.x>
                        appendToSlot = True
                        # <False> for the reflection means reflection to the left
                        reflection = False
                        # No example of a refelection to the left on the image <Main>,
                        # the example above with the reflection to right should give
                        # understanding what a reflection is about 
            if appendToSlot:
                # change the current slot and <self.originSlot>
                self.originSlot = slot
                slot = slots[index1]
                # Create a new part for the new slot
                # Note that the last part of <self.originSlot> (i.e. <self.originSlot.parts[-1]>)
                # ends at the new current <slot>
                slot.append(pv1.vertIndex, pv1.y, self.originSlot, reflection)
        
        def common_code(slot, vertsRange):
            """
            A helper function
            
            Actually create in-between vertices located on the slots for the segment between <pv1> and <pv2>,
            add the indices of the newly created vertices to the wall face <_wallIndices>.
            Also append those indices to the related slots and change the current slot in the cycle
            
            Args:
                slot (Slot): the current slot
                vertsRange (range): range of <slots> to create in-between vertices
            """
            vertIndex = len(verts) - 1
            # <vertIndex> is incremented positively
            # <vertIndexForSlots> is incremented negatively
            vertIndexForSlots = vertIndex + len(vertsRange)
            # <factorX> and <factorY> are used in calculations in the cycle below
            factorX = (v2.x - v1.x) / (pv2.x - pv1.x)
            factorY = (v2.y - v1.y) / (pv2.x - pv1.x)
            # <factorSlots> is used to calculate Y-coordinate in the profile coordinate system
            factorSlots = (pv2.y - pv1.y) / (pv2.x - pv1.x)
            # <reversed(vertsRange)> is actually a Python range of <slots>
            # to append the indices of the newly created vertices to the related slots
            for slotIndexVerts,slotIndex in zip(vertsRange, reversed(vertsRange)):
                vertIndex += 1
                factor = p[slotIndexVerts][0] - pv1.x
                verts.append(Vector((
                    v1.x + factor * factorX,
                    v1.y + factor * factorY,
                    footprint.roofVerticalPosition + footprint.roofHeight * p[slotIndexVerts][1]
                )))
                _wallIndices.append(vertIndex)
                #
                # fill <slots>
                #
                # append <vertIndex> to the last part of the current slot (i.e. to slot.parts[-1])
                slot.append(vertIndexForSlots)
                # change the current slot and <self.originSlot>
                self.originSlot = slot
                slot = slots[slotIndex]
                # Create a new part for the new slot
                # Note that the last part of <self.originSlot> (i.e. <self.originSlot.parts[-1]>)
                # ends at the new current <slot>
                y = pv1.y + factorSlots * (p[slotIndex][0] - pv1.x)
                slot.append(vertIndexForSlots, y, self.originSlot)
                self.onNewSlotVertex(slotIndex, vertIndexForSlots, y)
                # Child classes of <Slot> may use the following function call <slot.processWallFace(..)>
                # to do some stuff
                slot.processWallFace(_wallIndices, pv1, pv2)
                vertIndexForSlots -= 1
            # return the current slot
            return slot
        
        if index1 != index2:
            if index2 > index1:
                # Going from the left to the right
                # If the condition below isn't valid, there is no need to call <common_code(..)>
                if not pv2.onSlot or index1 != index2-1:
                    slot = common_code(
                        slot,
                        range(index2-1 if pv2.onSlot else index2, index1, -1)
                    )
            else:
                # Going from the right to the left
                # If the condition below isn't valid, there is no need to call <common_code(..)>
                if not pv1.onSlot or index2 != index1-1:
                    slot = common_code(
                        slot,
                        range(index2+1, index1 if pv1.onSlot else index1+1)
                    )
        # The wall face <_wallIndices> is ready,
        # append the closing vertex <pv1.vertIndex> to <_wallIndices> (if necessary!) and
        # append <_wallIndices> to <wallIndices>
        if appendPv1:
            _wallIndices.append(pv1.vertIndex)
        
        footprint.facades.append(
            Facade(
                footprint,
                _wallIndices,
                pv1.vector,
                self
            )
        )
        
        # append <pv2.vertIndex> to the last part of the current slot (i.e. to <slot.parts[-1]>)
        slot.append(pv2.vertIndex)
        # remember the current slot
        self.slot = slot
    
    def onNewSlotVertex(self, slotIndex, vertexIndex, y):
        """
        The method is called for every newly created in-between vertex <self.verts[vertexIndex]>
        located on the slot <self.slots[slotIndex]> between the neighbor profiled vertices.
        The vertex has Y-coordinate <y> in the profile coordinate system.
        
        The method can be overriden by a child class.
        """
        # The elements of the Python tuple below are described in code of the method
        # item_renderer/texture/roof_profile/RoofProfile/getUvs(..)
        self.roofVertexData[vertexIndex] = (
            True,
            slotIndex,
            y
        )
        # update <self.minY> and <self.maxY> if necessary
        if y < self.minY:
            self.minY = y
        elif y > self.maxY:
            self.maxY = y
    
    def onRoofForSlotCompleted(self, slotIndex):
        """
        The method is called when polygons defining roof parts
        for the slot <self.slots[slotIndex]> are completed.
        
        The method can be overriden by a child class.
        """
    
    def initFacadeItem(self, item):
        verts = item.building.renderInfo.verts
        indices = item.indices
        numVerts = len(indices)
        firstVert = verts[indices[0]]
        # a vector along the bottom side of the trapezoid
        bottomVec = verts[indices[1]] - firstVert
        heightLeft = verts[indices[-1]][2] - firstVert[2]
        heightRight = verts[indices[2]][2] - verts[indices[1]][2]
        # facade item width
        width = bottomVec.length
        if numVerts == 4:
            if heightLeft == heightRight:
                geometry = self.geometryRectangle
                # flat vertices coordinates on the facade surface (i.e. on the rectangle)
                uvs = geometry.getUvs(width, heightLeft)
            else:
                geometry = self.geometryTrapezoid
                # flat vertices coordinates on the facade surface (i.e. on the trapezoid)
                uvs = ( (0., 0.), (width, 0.), (width, heightRight), (0., heightLeft) )
        else:
            geometry = self.geometryTrapezoidChained
            # flat vertices coordinates on the facade surface (i.e. on the chained trapezoid)
            unitBottomVec = bottomVec/width
            # Now flat vertices coordinates on the facade surface:
            # first the vertices at the bottom and the next vertex,
            # then the rest of the vertices but the last one,
            # and finally the last vertex adjoining the left vertex at the bottom
            # A sum of several Python tuples gives a single Python tuple
            uvs =\
                ((0., 0.), (width, 0.), (width, heightRight)) +\
                tuple( ((verts[indices[i]]-firstVert).dot(unitBottomVec), verts[indices[i]][2]-firstVert[2]) for i in range(3,numVerts-1) ) +\
                ( (0., heightLeft), )
        
        item.width = width
        item.normal = bottomVec.cross(zAxis)/width
        item.geometry = geometry
        # assign uv-coordinates (i.e. surface coordinates on the facade plane)
        item.uvs = uvs
    
    def addRoofSide(self, indices, roofItem, slotIndex):
        roofItem.addRoofSide(
            indices,
            self.getUvs(indices, slotIndex) if self.setUvs else None,
            slotIndex
        )
    
    def getUvs(self, indices, slotIndex):
        roofVertexData = self.roofVertexData
        slopes = self.slopes
        #
        # Set texture coordinates <u> and <v>
        #
        # <roofVertexData[index]> is a Python tuple of three elements:
        # <roofVertexData[index][0]> indicates if the related roof vertex is located
        #     on the slot;
        # <roofVertexData[index][1]> is a slot index if <roofVertexData[index][0]> is equal to True;
        # <roofVertexData[index][1]> is a coordinate along profile part
        #     if <roofVertexData[index][0]> is equal to False;
        # <roofVertexData[index][2]> is a coordinate along Y-axis of the profile
        #     coordinate system
        return (
            (
                # U-coordinate: set it depending on the value of <slopes[slotIndex]>
                self.maxY - roofVertexData[index][2]\
                if slopes[slotIndex] else\
                roofVertexData[index][2] - self.minY,
                # V-coordinate
                (
                    0.\
                    if (slopes[slotIndex] and roofVertexData[index][1] == slotIndex) or\
                    (not slopes[slotIndex] and roofVertexData[index][1] == slotIndex+1) else\
                    self.partLength[slotIndex]
                )
                if roofVertexData[index][0] else\
                # the related roof vertex isn't located on the slot
                roofVertexData[index][1]
            )
            for index in indices
        )