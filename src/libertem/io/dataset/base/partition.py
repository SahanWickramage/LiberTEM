import itertools

import numpy as np

from libertem.common import Slice, Shape
from .tiling import DataTile, TilingScheme
from .meta import DataSetMeta
from .fileset import FileSet
from .backend import LocalFSMMapBackend
from .decode import Decoder


class WritablePartition:
    def get_write_handle(self):
        raise NotImplementedError()

    def delete(self):
        raise NotImplementedError()


class Partition(object):
    def __init__(
        self, meta: DataSetMeta, partition_slice: Slice,
    ):
        """
        Parameters
        ----------
        meta
            The `DataSet`'s `DataSetMeta` instance

        partition_slice
            The partition slice in non-flattened form

        fileset
            The files that are part of this partition (the FileSet may also contain files
            from the dataset which are not part of this partition, but that may harm performance)

        start_frame
            The index of the first frame of this partition (global coords)

        num_frames
            How many frames this partition should contain
        """
        self.meta = meta
        self.slice = partition_slice
        if partition_slice.shape.nav.dims != 1:
            raise ValueError("nav dims should be flat")

    @classmethod
    def make_slices(cls, shape, num_partitions):
        """
        partition a 3D dataset ("list of frames") along the first axis,
        yielding the partition slice, and additionally start and stop frame
        indices for each partition.
        """
        num_frames = shape.nav.size
        f_per_part = max(1, num_frames // num_partitions)

        c0 = itertools.count(start=0, step=f_per_part)
        c1 = itertools.count(start=f_per_part, step=f_per_part)
        for (start, stop) in zip(c0, c1):
            if start >= num_frames:
                break
            stop = min(stop, num_frames)
            part_slice = Slice(
                origin=(start,) + tuple([0] * shape.sig.dims),
                shape=Shape(((stop - start),) + tuple(shape.sig),
                            sig_dims=shape.sig.dims)
            )
            yield part_slice, start, stop

    def need_decode(self, read_dtype, roi):
        raise NotImplementedError()

    def validate_tiling_scheme(self, tiling_scheme):
        pass

    def get_tiles(self, tiling_scheme, dest_dtype="float32", roi=None):
        raise NotImplementedError()

    def get_base_shape(self):
        raise NotImplementedError()

    def __repr__(self):
        return "<%s>" % (
            self.__class__.__name__,
        )

    @property
    def dtype(self):
        return self.meta.dtype

    @property
    def shape(self):
        """
        the shape of the partition; dimensionality depends on format
        """
        return self.slice.shape.flatten_nav()

    def get_macrotile(self, dest_dtype="float32", roi=None):
        raise NotImplementedError()

    def adjust_tileshape(self, tileshape):
        raise NotImplementedError()

    def get_locations(self):
        raise NotImplementedError()


class BasePartition(Partition):
    """
    Base class with default implementations
    """
    def __init__(
        self, meta: DataSetMeta, partition_slice: Slice,
        fileset: FileSet, start_frame: int, num_frames: int
    ):
        """
        Parameters
        ----------
        meta
            The `DataSet`'s `DataSetMeta` instance

        partition_slice
            The partition slice in non-flattened form

        fileset
            The files that are part of this partition (the FileSet may also contain files
            from the dataset which are not part of this partition, but that may harm performance)

        start_frame
            The index of the first frame of this partition (global coords)

        num_frames
            How many frames this partition should contain
        """
        super().__init__(meta=meta, partition_slice=partition_slice)
        self._fileset = fileset.get_for_range(start_frame, start_frame + num_frames - 1)
        self._start_frame = start_frame
        self._num_frames = num_frames
        if num_frames <= 0:
            raise ValueError("invalid number of frames: %d" % num_frames)

    def get_locations(self):
        # Allow using any worker by default
        return None

    def adjust_tileshape(self, tileshape):
        return tileshape

    def get_base_shape(self):
        return (1,) + (1,) * (self.shape.sig.dims - 1) + (self.shape.sig[-1],)

    def get_macrotile(self, dest_dtype="float32", roi=None):
        '''
        Return a single tile for the entire partition.

        This is useful to support process_partiton() in UDFs and to construct dask arrays
        from datasets.
        '''

        tiling_scheme = TilingScheme.make_for_shape(
            tileshape=self.shape,
            dataset_shape=self.meta.shape,
        )

        try:
            return next(self.get_tiles(
                tiling_scheme=tiling_scheme,
                dest_dtype=dest_dtype,
                roi=roi,
            ))
        except StopIteration:
            tile_slice = Slice(
                origin=(self.slice.origin[0], 0, 0),
                shape=Shape((0,) + tuple(self.slice.shape.sig), sig_dims=2),
            )
            return DataTile(
                np.zeros(tile_slice.shape, dtype=dest_dtype),
                tile_slice=tile_slice,
                scheme_idx=0,
            )

    def need_decode(self, read_dtype, roi):
        io_backend = self._get_io_backend()
        return io_backend.need_copy(
            roi=roi, native_dtype=self.meta.raw_dtype, read_dtype=read_dtype
        )

    def _get_decoder(self) -> Decoder:
        return None

    def _get_read_ranges(self, tiling_scheme, roi=None):
        return self._fileset.get_read_ranges(
            start_at_frame=self._start_frame,
            stop_before_frame=self._start_frame + self._num_frames,
            tiling_scheme=tiling_scheme,
            dtype=self.meta.raw_dtype,
            roi=roi,
        )

    def _get_io_backend(self):
        return LocalFSMMapBackend(decoder=self._get_decoder())

    def get_tiles(self, tiling_scheme, dest_dtype="float32", roi=None):
        """
        Return a generator over all DataTiles contained in this Partition.

        Note
        ----
        The DataSet may reuse the internal buffer of a tile, so you should
        directly process the tile and not accumulate a number of tiles and then work
        on them.

        Parameters
        ----------

        tiling_scheme
            According to this scheme the data will be tiled

        dest_dtype : numpy dtype
            convert data to this dtype when reading

        roi : numpy.ndarray
            Boolean array that matches the dataset navigation shape to limit the region to work on.
            With a ROI, we yield tiles from a "compressed" navigation axis, relative to
            the beginning of the dataset. Compressed means, only frames that have a 1
            in the ROI are considered, and the resulting tile slices are from a coordinate
            system that has the shape `(np.count_nonzero(roi),)`.
        """
        dest_dtype = np.dtype(dest_dtype)
        self.validate_tiling_scheme(tiling_scheme)
        read_ranges = self._get_read_ranges(tiling_scheme, roi)
        io_backend = self._get_io_backend()

        yield from io_backend.get_tiles(
            tiling_scheme=tiling_scheme, fileset=self._fileset,
            read_ranges=read_ranges, roi=roi,
            native_dtype=self.meta.raw_dtype, read_dtype=dest_dtype
        )

    def __repr__(self):
        return "<%s [%d:%d]>" % (
            self.__class__.__name__,
            self._start_frame, self._start_frame + self._num_frames
        )
